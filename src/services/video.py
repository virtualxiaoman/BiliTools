"""
视频服务：获取视频信息、下载视频/音频/封面。

取代旧 `src/video.py` 的 `BiliVideo`，核心区别：
- 数据通过 `fetch_info()` 返回 `VideoInfo` 模型，不再挂在实例上；
- 下载只接受「保存目录」，文件名由后端按 `[标题](BV号).扩展名` 规则生成；
- 失败抛异常（BiliError 体系），不再返回 False/None。

[使用方法]
    service = VideoService()   # 使用默认 cookie
    info = service.fetch_info("BV1ov42117yC")
    result = service.download_video_with_audio("BV1ov42117yC")
    print(result.path)
"""

import logging
from pathlib import Path
from typing import Optional, Union

from src.api.auth import get_wbi
from src.api.errors import FFmpegNotFoundError
from src.api.session import BiliSession
from src.config.constants import DASH_FNVAL
from src.config.path import VIDEO_OUTPUT_DIR
from src.models.download_model import (
    AudioStream,
    DashStreams,
    DownloadResult,
    VideoQuality,
    VideoStream,
)
from src.models.video_model import VideoInfo, VideoPage, VideoSeason, VideoSeasonEpisode
from src.services.archive import ArchiveService
from src.urls.video_urls import VideoUrls
from src.util.downloader import ProgressCallback, download_stream, ffmpeg_available, merge_video_audio
from src.util.filename import build_download_filename, build_multi_page_filename
from src.util.progress import BatchProgress

logger = logging.getLogger(__name__)


class VideoService:
    """B 站视频的获取与下载服务。"""

    def __init__(
        self,
        session: Optional[BiliSession] = None,
        default_dir: Path = VIDEO_OUTPUT_DIR,
    ):
        """
        :param session: BiliSession 实例，None 时创建（使用默认 cookie）
        :param default_dir: 默认下载目录，调用下载方法未指定 dir 时使用
        """
        self.session = session if session is not None else BiliSession()
        self.default_dir = Path(default_dir)

    # ---- 视频信息 ----

    def fetch_info(self, bvid: str) -> VideoInfo:
        """获取视频基本信息（标题/统计/作者等），并填充 cid。

        :param bvid: BV号
        :return: VideoInfo
        """
        data = self.session.get(VideoUrls.VIEW, params={"bvid": bvid})
        return VideoInfo.from_view_json(data)

    def fetch_tags(self, bvid: str) -> list:
        """获取视频标签（tag_name 列表）。

        :param bvid: BV号
        :return: 标签名列表
        """
        data = self.session.get(VideoUrls.TAG, params={"bvid": bvid})
        return [tag["tag_name"] for tag in data]

    def fetch_info_with_tags(self, bvid: str) -> VideoInfo:
        """获取视频基本信息 + 标签（一次调用组装完整信息）。

        :param bvid: BV号
        :return: VideoInfo（含 tags）
        """
        info = self.fetch_info(bvid)
        info.tags = self.fetch_tags(bvid)
        return info

    # ---- 播放流 ----

    def get_playurl(self, bvid: str, cid: int, fnval: int = DASH_FNVAL) -> DashStreams:
        """获取视频 DASH 播放流（视频/音频直链）。

        :param bvid: BV号
        :param cid: 视频 cid（鉴权参数）
        :param fnval: 置为 4048 会取到所有可用 DASH 视频流
        :return: DashStreams（video 按清晰度降序，audio 按码率降序）
        """
        params = {
            "bvid": bvid,
            "cid": cid,
            "qn": 120,  # 4K（该值在DASH格式下无效，因为DASH会返回所有可用分辨率的流地址，由 pick_video 挑选）
            "fnver": 0,  # 定值
            "fnval": fnval,  # 设置为4048则会所有可用 DASH 视频流。
            "fourk": 1,  # 是否允许4k。取0代表画质最高1080P（这是不传递fourk时的默认值），取1代表最高4K
            "platform": "pc",  # 平台。pc或html5
            "high_quality": 1,  # 当platform=html5时，此值为1可使画质为1080p
        }
        get_wbi(params)  # 原地追加 wts 与 w_rid
        data = self.session.get(VideoUrls.PLAY, params=params)

        videos = [
            VideoStream(
                url=v["baseUrl"],
                codecs=v.get("codecs", ""),
                width=v.get("width", 0),
                height=v.get("height", 0),
                quality=v.get("id", 0),
                frame_rate=v.get("frameRate", ""),
                size=v.get("size", 0),
            )
            for v in data["dash"]["video"]
        ]
        audios = [
            AudioStream(
                url=a["baseUrl"],
                codecs=a.get("codecs", ""),
                bandwidth=a.get("bandwidth", 0),
                size=a.get("size", 0),
            )
            for a in data["dash"]["audio"]
        ]
        # DashStreams 构造时自动按 quality / bandwidth 降序排序
        return DashStreams(video=videos, audio=audios)

    # ---- 下载 ----

    def _resolve_page(self, info: VideoInfo, page: int = 1) -> VideoPage:
        """根据分P序号从 VideoInfo 中解析出目标分P。

        :param page: 分P序号（从1开始）。多P视频指定具体P；单P视频默认为1
        :return: VideoPage
        :raises ValueError: 分P不存在
        """
        if info.pages:
            for p in info.pages:
                if p.page == page:
                    return p
            raise ValueError(f"视频 {info.bvid} 没有第 {page} 分P（共 {len(info.pages)} 个分P）。")
        # 无 pages 数据时（理论上不会发生，from_view_json 总会填充），退回 cid
        if page != 1:
            raise ValueError(f"视频 {info.bvid} 没有分P信息，无法指定第 {page} 分P。")
        return VideoPage(page=1, cid=info.cid or 0, part=info.title)

    def _fetch_streams(self, bvid: str, page: int = 1) -> tuple[VideoInfo, DashStreams]:
        """获取视频信息 + 指定分P的 DASH 流（download_* 系列共用，避免重复请求）。"""
        info = self.fetch_info(bvid)
        target = self._resolve_page(info, page)
        if target.cid is None or target.cid == 0:
            raise ValueError(f"视频 {bvid} 第 {page} 分P 的 cid 获取失败，无法下载。")
        return info, self.get_playurl(bvid, target.cid)

    def _default_filename(self, info: VideoInfo, bvid: str, page: int, ext: str) -> str:
        """根据是否多P生成默认文件名：单P用 `[标题](BV号).ext`，多P用 `[标题]-Pxx-[part](BV号).ext`。"""
        if page == 1 and not info.is_multi_page:
            return build_download_filename(info.title, bvid, ext)
        target = self._resolve_page(info, page)
        return build_multi_page_filename(info.title, bvid, target.page, target.part, ext)

    def _auto_progress(self, name: str, progress: Optional[BatchProgress] = None,
                       progress_cb: Optional[ProgressCallback] = None):
        """单独调用下载方法时，若调用方未传 progress/progress_cb，则自动创建一个进度条。

        :return: (progress, 是否自动创建)。自动创建的调用方需在完成后调用 finish()。
        """
        if progress is None and progress_cb is None:
            p = BatchProgress(n=1, label="下载")
            p.start(1, name)
            return p, True
        return progress, False

    def download_video(
        self,
        bvid: str,
        dir: Optional[Path] = None,
        *,
        page: int = 1,
        quality: VideoQuality = VideoQuality.HD4K,
        progress_cb: Optional[ProgressCallback] = None,
        progress: Optional[BatchProgress] = None,
        filename: Optional[str] = None,
    ) -> DownloadResult:
        """下载视频流（无音频）。文件名为 `[标题](BV号).{实际格式}`，多P时含 P 序号。

        :param bvid: BV号
        :param dir: 保存目录。None 时使用默认下载目录
        :param page: 分P序号（从1开始），多P视频指定要下载的P
        :param quality: 目标清晰度（精确匹配，匹配不到回退到最高可用）
        :param progress_cb: 进度回调 (downloaded, total)
        :param progress: BatchProgress 进度显示（与 progress_cb 二选一，通常由批量接口传入）
        :param filename: 自定义文件名（含扩展名），None 时按统一命名规则生成
        :return: DownloadResult
        """
        info, dash = self._fetch_streams(bvid, page)
        stream = dash.pick_video(quality)
        if stream is None:
            raise ValueError(f"视频 {bvid} 第 {page} 分P 没有可用的视频流。")

        save_dir = Path(dir) if dir is not None else self.default_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        if filename is None:
            filename = self._default_filename(info, bvid, page, stream.ext)
        save_path = save_dir / filename

        # 单独调用时自动显示进度条
        progress, auto_progress = self._auto_progress(filename, progress, progress_cb)

        if progress:
            picked = VideoQuality.from_qn(stream.quality)
            if picked is not None:
                progress.set_quality(picked)
        size = download_stream(
            stream.url, save_path, self.session.session.headers,
            progress_cb=progress.make_stream_callback() if progress else progress_cb,
        )
        if auto_progress:
            progress.finish()
        return DownloadResult(path=save_path, media_type="video", size=size)

    def download_audio(
        self,
        bvid: str,
        dir: Optional[Path] = None,
        *,
        page: int = 1,
        progress_cb: Optional[ProgressCallback] = None,
        progress: Optional[BatchProgress] = None,
        filename: Optional[str] = None,
    ) -> DownloadResult:
        """下载音频流。文件名为 `[标题](BV号).{实际格式}`，多P时含 P 序号。

        :param bvid: BV号
        :param dir: 保存目录。None 时使用默认下载目录
        :param page: 分P序号（从1开始），多P视频指定要下载的P
        :param progress_cb: 进度回调 (downloaded, total)
        :param progress: BatchProgress 进度显示（与 progress_cb 二选一，通常由批量接口传入）
        :param filename: 自定义文件名（含扩展名），None 时按统一命名规则生成
        :return: DownloadResult
        """
        info, dash = self._fetch_streams(bvid, page)
        stream = dash.best_audio()
        if stream is None:
            raise ValueError(f"视频 {bvid} 第 {page} 分P 没有可用的音频流。")

        save_dir = Path(dir) if dir is not None else self.default_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        if filename is None:
            filename = self._default_filename(info, bvid, page, stream.ext)
        save_path = save_dir / filename

        # 单独调用时自动显示进度条
        progress, auto_progress = self._auto_progress(filename, progress, progress_cb)

        size = download_stream(
            stream.url, save_path, self.session.session.headers,
            progress_cb=progress.make_stream_callback() if progress else progress_cb,
        )
        if auto_progress:
            progress.finish()
        return DownloadResult(path=save_path, media_type="audio", size=size)

    def download_video_with_audio(
        self,
        bvid: str,
        dir: Optional[Path] = None,
        *,
        page: int = 1,
        quality: VideoQuality = VideoQuality.HD4K,
        keep_parts: bool = False,
        progress_cb: Optional[ProgressCallback] = None,
        progress: Optional[BatchProgress] = None,
        filename: Optional[str] = None,
    ) -> DownloadResult:
        """下载视频流 + 音频流，并用 ffmpeg 合成为一个文件。

        视频流与音频流先下载到临时目录（`<dir>/.tmp/`），合成成功后默认删除。
        [注意] 合成依赖系统安装 ffmpeg，未安装时会在下载前直接报错。

        :param bvid: BV号
        :param dir: 保存目录。None 时使用默认下载目录
        :param page: 分P序号（从1开始），多P视频指定要下载的P
        :param quality: 目标清晰度（精确匹配，匹配不到回退到最高可用）
        :param keep_parts: 是否保留合成前的视频/音频临时文件（默认删除）
        :param progress_cb: 进度回调 (downloaded, total)。传入时将进度转发给回调
        :param progress: BatchProgress 进度显示（与 progress_cb 二选一，通常由批量接口传入）
        :param filename: 自定义文件名（含扩展名），None 时按统一命名规则生成
        :return: DownloadResult
        :raises FFmpegNotFoundError: 系统未安装 ffmpeg
        """
        import tempfile

        # 预检 ffmpeg：避免下载完几十 MB 后才报错
        if not ffmpeg_available():
            raise FFmpegNotFoundError("未检测到 ffmpeg，无法进行音视频合成。请先安装 ffmpeg 并加入系统 PATH。")

        info, dash = self._fetch_streams(bvid, page)
        video_stream = dash.pick_video(quality)
        audio_stream = dash.best_audio()
        if video_stream is None or audio_stream is None:
            raise ValueError(f"视频 {bvid} 第 {page} 分P 的视频流或音频流不可用，无法合成。")

        save_dir = Path(dir) if dir is not None else self.default_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        if filename is None:
            filename = self._default_filename(info, bvid, page, "mp4")
        save_path = save_dir / filename

        # 单独调用时自动显示进度条
        progress, auto_progress = self._auto_progress(filename, progress, progress_cb)

        if progress:
            picked = VideoQuality.from_qn(video_stream.quality)
            if picked is not None:
                progress.set_quality(picked)

        # 临时目录下载音视频流
        with tempfile.TemporaryDirectory(prefix="bilitools_", dir=save_dir) as tmp:
            tmp_dir = Path(tmp)
            video_tmp = tmp_dir / f"video.{video_stream.ext}"
            audio_tmp = tmp_dir / f"audio.{audio_stream.ext}"
            # 进度：视频流+音频流字节增量累加（跨流不重置，总大小为两流之和）
            _stream_state = {"id": 0, "last": 0}

            def _stream_cb(done: int, total: Optional[int]) -> None:
                if progress:
                    # 每个流的 done 是流内绝对值，算增量后按流累加；流切换时 last 归零由外层处理
                    delta = done - _stream_state["last"]
                    progress.add(delta, total, stream_id=_stream_state["id"])
                    _stream_state["last"] = done
                elif progress_cb:
                    progress_cb(done, total)

            download_stream(
                video_stream.url, video_tmp, self.session.session.headers,
                progress_cb=_stream_cb,
            )
            if progress:
                progress.status("视频流下载完成，正在下载音频流...")
                _stream_state["id"] = 1
                _stream_state["last"] = 0  # 音频流从头计数
            download_stream(
                audio_stream.url, audio_tmp, self.session.session.headers,
                progress_cb=_stream_cb,
            )
            if progress:
                progress.status("正在用 ffmpeg 合成音视频...")
            merge_video_audio(video_tmp, audio_tmp, save_path, progress_cb=progress_cb)
            if keep_parts:
                # 保留临时文件到同级目录（重命名避免冲突）
                video_tmp.replace(save_dir / f"{save_path.stem}.video.{video_stream.ext}")
                audio_tmp.replace(save_dir / f"{save_path.stem}.audio.{audio_stream.ext}")

        if auto_progress:
            progress.finish()
        return DownloadResult(path=save_path, media_type="video", size=save_path.stat().st_size)

    def download_cover(
        self,
        bvid: str,
        dir: Optional[Path] = None,
        *,
        progress_cb: Optional[ProgressCallback] = None,
        progress: Optional[BatchProgress] = None,
        filename: Optional[str] = None,
    ) -> DownloadResult:
        """下载视频封面。文件名为 `[标题](BV号).jpg/png`。

        :param bvid: BV号
        :param dir: 保存目录。None 时使用默认下载目录
        :param progress_cb: 进度回调 (downloaded, total)
        :param progress: BatchProgress 进度显示（与 progress_cb 二选一，通常由批量接口传入）
        :param filename: 自定义文件名（含扩展名），None 时按统一命名规则生成
        :return: DownloadResult
        """
        info = self.fetch_info(bvid)
        if not info.pic:
            raise ValueError(f"视频 {bvid} 的封面地址获取失败。")

        save_dir = Path(dir) if dir is not None else self.default_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        if filename is None:
            ext = "png" if info.pic.endswith(".png") else "jpg"
            filename = build_download_filename(info.title, bvid, ext)
        save_path = save_dir / filename

        # 单独调用时自动显示进度条
        progress, auto_progress = self._auto_progress(filename, progress, progress_cb)

        content = self.session.get_raw(info.pic)
        save_path.write_bytes(content)
        if progress:
            progress.update(len(content), len(content))
        elif progress_cb:
            progress_cb(len(content), len(content))
        if auto_progress:
            progress.finish()
        return DownloadResult(path=save_path, media_type="cover", size=len(content))

    def download_all_pages(
        self,
        bvid: str,
        dir: Optional[Path] = None,
        *,
        quality: VideoQuality = VideoQuality.HD4K,
        media_type: str = "video_with_audio",
        progress_cb: Optional[ProgressCallback] = None,
        progress: Optional[BatchProgress] = None,
    ) -> list:
        """下载多P视频的全部分P（单P视频等价于 download_video_with_audio）。

        :param bvid: BV号
        :param dir: 保存目录。None 时使用默认下载目录
        :param quality: 目标清晰度（精确匹配，匹配不到回退到最高可用）
        :param media_type: 下载类型：video / audio / video_with_audio / cover
        :param progress_cb: 进度回调 (downloaded, total)
        :param progress: BatchProgress 进度显示；None 时自动创建
        :return: DownloadResult 列表（每个分P一个）
        """
        info = self.fetch_info(bvid)
        if not info.pages:
            raise ValueError(f"视频 {bvid} 没有分P信息，无法批量下载。")

        n = len(info.pages)
        progress = progress or BatchProgress(n=n, label=f"视频 {bvid}")
        results = []
        for i, page_obj in enumerate(info.pages, 1):
            # 进度显示用的文件名（与最终保存名一致）
            display_ext = {"video": "mp4", "audio": "m4a", "cover": "jpg"}.get(media_type, "mp4")
            display_name = self._default_filename(info, bvid, page_obj.page, display_ext)
            progress.start(i, display_name)
            logger.info("[VideoService] 正在下载 %s 第 %d/%d 分P：%s",
                        bvid, page_obj.page, n, page_obj.part)
            if media_type == "video":
                results.append(self.download_video(bvid, dir, page=page_obj.page, quality=quality,
                                                   progress_cb=progress_cb, progress=progress))
            elif media_type == "audio":
                results.append(self.download_audio(bvid, dir, page=page_obj.page,
                                                   progress_cb=progress_cb, progress=progress))
            elif media_type == "cover":
                results.append(self.download_cover(bvid, dir, progress_cb=progress_cb, progress=progress))
            else:  # video_with_audio
                results.append(self.download_video_with_audio(bvid, dir, page=page_obj.page,
                                                              quality=quality, progress_cb=progress_cb,
                                                              progress=progress))
            progress.finish()
        return results

    def fetch_season(self, bvid: Optional[str] = None, season_id: Optional[int] = None,
                     mid: int = 0) -> Optional[VideoSeason]:
        """获取合集信息（含合集内全部稿件结构）。bvid 与 season_id 任选其一。

        - 传 `bvid`：从该视频的 `ugc_season` 反查合集（任意 UP 主的合集，前提是该视频属于合集）；
        - 传 `season_id`：按合集 sid 查询（任意 UP 主的合集，mid 用于定位）。

        :param bvid: 合集内任意一个视频的BV号
        :param season_id: 合集 sid
        :param mid: season_id 方式下合集所属用户UID，0 时尝试用当前登录用户
        :return: VideoSeason，视频不属于合集（或合集无视频）时返回 None
        """
        if season_id is not None:
            try:
                data = ArchiveService(self.session).get_season_by_id(season_id, mid)
            except ValueError:
                return None
            meta = data.get("meta") or {}
            episodes = []
            for a in data.get("archives", []):
                bvid = a.get("bvid", "")
                # archives 条目不含分P信息，补一次 fetch_info 拿完整 pages
                pages = self.fetch_info(bvid).pages if bvid else []
                first_cid = pages[0].cid if pages else 0
                episodes.append(VideoSeasonEpisode(
                    bvid=bvid,
                    aid=a.get("aid", 0),
                    cid=first_cid,
                    title=a.get("title", ""),
                    pages=pages,
                ))
            return VideoSeason(
                id=meta.get("season_id", season_id),
                title=meta.get("title", ""),
                mid=meta.get("mid", 0),
                ep_count=meta.get("total", len(episodes)),
                episodes=episodes,
            )
        if bvid:
            return self.fetch_info(bvid).season
        raise ValueError("fetch_season 需要 bvid 或 season_id 至少一个参数")

    def download_season(
        self,
        bvid: Optional[str] = None,
        dir: Optional[Path] = None,
        *,
        season_id: Optional[int] = None,
        mid: int = 0,
        quality: VideoQuality = VideoQuality.HD4K,
        media_type: str = "video_with_audio",
        progress_cb: Optional[ProgressCallback] = None,
        progress: Optional[BatchProgress] = None,
    ) -> list:
        """下载整个合集。`bvid` 与 `season_id` 任选其一。

        - 传 `bvid`：从合集内任意一个视频进入，反查合集并下载全部稿件；
        - 传 `season_id`：按合集 sid 直接下载（如 sid=8683221 或 sid=1717000）。

        每个稿件若有多个分P，则逐P下载。文件保存到 `<dir>/<合集标题>/`。

        :param bvid: 合集内任意一个视频的BV号
        :param dir: 保存根目录。None 时使用默认下载目录
        :param season_id: 合集 sid
        :param mid: season_id 方式下合集所属用户UID，0 时尝试用当前登录用户
        :param quality: 目标清晰度（精确匹配，匹配不到回退到最高可用）
        :param media_type: 下载类型：video / audio / video_with_audio / cover
        :param progress_cb: 进度回调 (downloaded, total)
        :param progress: BatchProgress 进度显示；None 时自动创建
        :return: DownloadResult 列表
        :raises ValueError: 无法定位合集
        """
        season = self.fetch_season(bvid, season_id, mid)
        if season is None or not season.episodes:
            loc = f"bvid={bvid}" if bvid else f"season_id={season_id}"
            raise ValueError(f"{loc} 无法定位到合集，请确认参数正确。")

        save_dir = (Path(dir) if dir is not None else self.default_dir) / season.title
        save_dir.mkdir(parents=True, exist_ok=True)

        # 计算总共要下载的文件数（多P稿件按分P数计），驱动进度
        file_count = sum(len(ep.pages) if ep.is_multi_page else 1 for ep in season.episodes)
        progress = progress or BatchProgress(n=file_count, label=f"合集「{season.title}」")
        results = []
        file_idx = 0
        for episode in season.episodes:
            logger.info("[VideoService] 合集「%s」下载：%s", season.title, episode.title)
            if episode.is_multi_page:
                # 合集内多P稿件：逐P下载
                for page_obj in episode.pages:
                    file_idx += 1
                    info = self.fetch_info(episode.bvid)
                    display_name = self._default_filename(info, episode.bvid, page_obj.page, "mp4")
                    progress.start(file_idx, display_name)
                    results.append(self.download_video_with_audio(
                        episode.bvid, save_dir, page=page_obj.page, quality=quality,
                        progress_cb=progress_cb, progress=progress,
                    ))
                    progress.finish()
            else:
                file_idx += 1
                info = self.fetch_info(episode.bvid)
                display_ext = {"video": "mp4", "audio": "m4a", "cover": "jpg"}.get(media_type, "mp4")
                display_name = self._default_filename(info, episode.bvid, 1, display_ext)
                progress.start(file_idx, display_name)
                if media_type == "video":
                    results.append(self.download_video(episode.bvid, save_dir, quality=quality,
                                                       progress_cb=progress_cb, progress=progress))
                elif media_type == "audio":
                    results.append(self.download_audio(episode.bvid, save_dir,
                                                       progress_cb=progress_cb, progress=progress))
                elif media_type == "cover":
                    results.append(self.download_cover(episode.bvid, save_dir,
                                                       progress_cb=progress_cb, progress=progress))
                else:  # video_with_audio
                    results.append(self.download_video_with_audio(episode.bvid, save_dir, quality=quality,
                                                                  progress_cb=progress_cb, progress=progress))
                progress.finish()
        return results

    # ---- 统一下载接口 ----

    def download(self, bvid: str, dir: Optional[Path] = None) -> list:
        """统一下载入口：只接受 bvid，自动决定下载范围，使用最高清晰度并显示进度。

        规则：
        - 若该视频**属于某个合集**：下载合集内全部视频（每个视频有分P则逐P下载）；
        - 否则：下载该视频本身（有分P则下载全部分P）。
        默认使用最高清晰度（HD4K，无 4K 时自动回退到可用最高档），合成音视频（ffmpeg）。

        [使用方法]
            service.download("BV1ov42117yC")        # 单视频（含分P）
            service.download("BV1Q43w6QETb")        # 属于合集「洛天依·纯蓝幻乐」→ 下载整个合集

        :param bvid: 视频 BV 号
        :param dir: 保存根目录。None 时使用默认下载目录
        :return: DownloadResult 列表
        """
        info = self.fetch_info(bvid)
        if info.season and info.season.episodes:
            # 属于合集：下载整个合集
            return self.download_season(bvid=bvid, dir=dir, quality=VideoQuality.HD4K)
        # 单视频（含多P）：下载全部分P
        return self.download_all_pages(bvid, dir, quality=VideoQuality.HD4K)

    def download_fav(
        self,
        fid: Optional[Union[int, str]] = None,
        dir: Optional[Path] = None,
        *,
        mode: str = "video",
        quality: VideoQuality = VideoQuality.HD4K,
    ) -> list:
        """下载整个收藏夹的全部视频（有声音）或仅音频。

        逐个下载收藏夹内的视频，保存到 `<dir>/<收藏夹名称>/`（默认 `output/video/<收藏夹名称>/`）。
        每个视频若有分P则逐P下载。下载带进度显示（含清晰度标签）。

        [使用方法]
            service = VideoService()
            # 下载收藏夹全部视频（含音频合成），URL 或 media_id 均可
            service.download_fav("https://space.bilibili.com/506925078/favlist?fid=3953119978&ftype=create")
            service.download_fav(3953119978)
            # 仅下载音频（本地缓存听歌）
            service.download_fav(3953119978, mode="audio")

        :param fid: 收藏夹 media_id 或收藏夹页面 URL
        :param dir: 保存根目录。None 时使用默认下载目录
        :param mode: video（下载视频+音频合成，默认）或 audio（仅下载音频流）
        :param quality: 目标清晰度（精确匹配，默认 HD4K 最高）
        :return: DownloadResult 列表
        """
        from src.services.fav import FavService

        fav = FavService(self.session)
        info = fav.get_fav_info(fid)
        bvids = fav.get_fav_bv(fid)
        if not bvids:
            raise ValueError(f"收藏夹「{info.title}」没有视频。")

        save_dir = (Path(dir) if dir is not None else self.default_dir) / info.title
        save_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for bvid in bvids:
            logger.info("[VideoService] 收藏夹「%s」下载：%s", info.title, bvid)
            if mode == "audio":
                results.extend(self.download_all_pages(bvid, save_dir, quality=quality, media_type="audio"))
            else:  # video
                results.extend(self.download_all_pages(bvid, save_dir, quality=quality))
        return results

    # ---- UP主空间 ----

    def _resolve_mid(self, mid: Optional[Union[int, str]]) -> int:
        """接受 mid 或 UP主空间 URL，统一返回 mid。"""
        if mid is None:
            raise ValueError("需要提供 mid 或 UP主空间 URL")
        s = str(mid).strip()
        # https://space.bilibili.com/249056021 或带路径
        if s.startswith("http://") or s.startswith("https://"):
            import re
            match = re.search(r"space\.bilibili\.com/(\d+)", s)
            if not match:
                raise ValueError(f"无法从空间 URL 解析 mid：{s}")
            return int(match.group(1))
        return int(s)

    def list_up_videos(self, mid: Optional[Union[int, str]] = None, ps: int = 30) -> list:
        """获取某个 UP 主空间的全部视频 BV 号列表（分页翻到底）。

        [使用方法]:
            service = VideoService()
            bvs = service.list_up_videos(249056021)
            bvs = service.list_up_videos("https://space.bilibili.com/249056021")

        :param mid: UP主 mid 或空间 URL
        :param ps: 每页数量（最大 50）
        :return: 视频bv号列表
        """
        from src.api.auth import get_wbi
        from src.urls.user_urls import UserUrls

        mid = self._resolve_mid(mid)
        bvids = []
        pn = 1
        while True:
            params = {"mid": mid, "pn": pn, "ps": ps, "order": "pubdate"}
            get_wbi(params)  # 原地追加 wts 与 w_rid
            data = self.session.get(UserUrls.SPACE_ARC_SEARCH, params=params)
            vlist = data.get("list", {}).get("vlist", [])
            bvids.extend(v.get("bvid") for v in vlist)
            total = data.get("page", {}).get("count", 0)
            if len(bvids) >= total or not vlist:
                break
            pn += 1
            import time
            time.sleep(0.3)  # 避免风控
        return bvids

    def download_up(
        self,
        mid: Optional[Union[int, str]] = None,
        dir: Optional[Path] = None,
        *,
        mode: str = "video",
        quality: VideoQuality = VideoQuality.HD4K,
    ) -> list:
        """下载某个 UP 主空间的全部视频（有声音）或仅音频。

        逐个下载该 UP 主的所有投稿，保存到 `<dir>/<UP主昵称>/`（默认 `output/video/<昵称>/`）。
        每个视频若有分P则逐P下载，带进度显示。

        [使用方法]
            service = VideoService()
            # 下载 UP 主全部视频（含音频合成），URL 或 mid 均可
            service.download_up("https://space.bilibili.com/249056021")
            service.download_up(249056021)
            # 仅下载音频
            service.download_up(249056021, mode="audio")

        :param mid: UP主 mid 或空间 URL
        :param dir: 保存根目录。None 时使用默认下载目录
        :param mode: video（下载视频+音频合成，默认）或 audio（仅下载音频流）
        :param quality: 目标清晰度（精确匹配，默认 HD4K 最高）
        :return: DownloadResult 列表
        """
        from src.services.user import UserService

        mid = self._resolve_mid(mid)
        bvids = self.list_up_videos(mid)
        if not bvids:
            raise ValueError(f"UP主 {mid} 没有视频。")

        up_name = UserService(self.session).get_name(mid) or f"up_{mid}"
        save_dir = (Path(dir) if dir is not None else self.default_dir) / up_name
        save_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for bvid in bvids:
            logger.info("[VideoService] UP主「%s」下载：%s", up_name, bvid)
            if mode == "audio":
                results.extend(self.download_all_pages(bvid, save_dir, quality=quality, media_type="audio"))
            else:  # video
                results.extend(self.download_all_pages(bvid, save_dir, quality=quality))
        return results
