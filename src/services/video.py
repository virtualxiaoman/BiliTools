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
from typing import Optional

from src.api.auth import get_wbi
from src.api.errors import FFmpegNotFoundError
from src.api.session import BiliSession
from src.config.constants import DASH_FNVAL
from src.config.path import VIDEO_OUTPUT_DIR
from src.models.download import (
    AudioStream,
    DashStreams,
    DownloadResult,
    VideoQuality,
    VideoStream,
)
from src.models.video import VideoInfo
from src.urls.video import VideoUrls
from src.util.downloader import ProgressCallback, download_stream, ffmpeg_available, merge_video_audio
from src.util.filename import build_download_filename

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

    def _fetch_streams(self, bvid: str) -> tuple[VideoInfo, DashStreams]:
        """获取视频信息 + DASH 流（download_* 系列共用，避免重复请求）。"""
        info = self.fetch_info(bvid)
        if info.cid is None:
            raise ValueError(f"视频 {bvid} 的 cid 获取失败，无法下载。")
        return info, self.get_playurl(bvid, info.cid)

    def download_video(
        self,
        bvid: str,
        dir: Optional[Path] = None,
        *,
        quality: VideoQuality = VideoQuality.P1080,
        progress_cb: Optional[ProgressCallback] = None,
        filename: Optional[str] = None,
    ) -> DownloadResult:
        """下载视频流（无音频）。文件名为 `[标题](BV号).{实际格式}`。

        :param bvid: BV号
        :param dir: 保存目录。None 时使用默认下载目录
        :param quality: 期望的最小清晰度
        :param progress_cb: 进度回调 (downloaded, total)
        :param filename: 自定义文件名（含扩展名），None 时按统一命名规则生成
        :return: DownloadResult
        """
        info, dash = self._fetch_streams(bvid)
        stream = dash.pick_video(quality)
        if stream is None:
            raise ValueError(f"视频 {bvid} 没有可用的视频流。")

        save_dir = Path(dir) if dir is not None else self.default_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        if filename is None:
            filename = build_download_filename(info.title, bvid, stream.ext)
        save_path = save_dir / filename

        size = download_stream(
            stream.url, save_path, self.session.session.headers,
            progress_cb=progress_cb,
        )
        return DownloadResult(path=save_path, media_type="video", size=size)

    def download_audio(
        self,
        bvid: str,
        dir: Optional[Path] = None,
        *,
        progress_cb: Optional[ProgressCallback] = None,
        filename: Optional[str] = None,
    ) -> DownloadResult:
        """下载音频流。文件名为 `[标题](BV号).{实际格式}`。

        :param bvid: BV号
        :param dir: 保存目录。None 时使用默认下载目录
        :param progress_cb: 进度回调 (downloaded, total)
        :param filename: 自定义文件名（含扩展名），None 时按统一命名规则生成
        :return: DownloadResult
        """
        info, dash = self._fetch_streams(bvid)
        stream = dash.best_audio()
        if stream is None:
            raise ValueError(f"视频 {bvid} 没有可用的音频流。")

        save_dir = Path(dir) if dir is not None else self.default_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        if filename is None:
            filename = build_download_filename(info.title, bvid, stream.ext)
        save_path = save_dir / filename

        size = download_stream(
            stream.url, save_path, self.session.session.headers,
            progress_cb=progress_cb,
        )
        return DownloadResult(path=save_path, media_type="audio", size=size)

    def download_video_with_audio(
        self,
        bvid: str,
        dir: Optional[Path] = None,
        *,
        quality: VideoQuality = VideoQuality.P1080,
        keep_parts: bool = False,
        progress_cb: Optional[ProgressCallback] = None,
        filename: Optional[str] = None,
    ) -> DownloadResult:
        """下载视频流 + 音频流，并用 ffmpeg 合成为一个文件。

        视频流与音频流先下载到临时目录（`<dir>/.tmp/`），合成成功后默认删除。
        [注意] 合成依赖系统安装 ffmpeg，未安装时会在下载前直接报错。

        :param bvid: BV号
        :param dir: 保存目录。None 时使用默认下载目录
        :param quality: 期望的最小清晰度
        :param keep_parts: 是否保留合成前的视频/音频临时文件（默认删除）
        :param progress_cb: 进度回调 (downloaded, total)
        :param filename: 自定义文件名（含扩展名），None 时按统一命名规则生成
        :return: DownloadResult
        :raises FFmpegNotFoundError: 系统未安装 ffmpeg
        """
        import tempfile

        # 预检 ffmpeg：避免下载完几十 MB 后才报错
        if not ffmpeg_available():
            raise FFmpegNotFoundError("未检测到 ffmpeg，无法进行音视频合成。请先安装 ffmpeg 并加入系统 PATH。")

        info, dash = self._fetch_streams(bvid)
        video_stream = dash.pick_video(quality)
        audio_stream = dash.best_audio()
        if video_stream is None or audio_stream is None:
            raise ValueError(f"视频 {bvid} 的视频流或音频流不可用，无法合成。")

        save_dir = Path(dir) if dir is not None else self.default_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        if filename is None:
            filename = build_download_filename(info.title, bvid, "mp4")
        save_path = save_dir / filename

        # 临时目录下载音视频流
        with tempfile.TemporaryDirectory(prefix="bilitools_", dir=save_dir) as tmp:
            tmp_dir = Path(tmp)
            video_tmp = tmp_dir / f"video.{video_stream.ext}"
            audio_tmp = tmp_dir / f"audio.{audio_stream.ext}"
            download_stream(
                video_stream.url, video_tmp, self.session.session.headers,
                progress_cb=progress_cb,
            )
            download_stream(
                audio_stream.url, audio_tmp, self.session.session.headers,
                progress_cb=progress_cb,
            )
            merge_video_audio(video_tmp, audio_tmp, save_path, progress_cb=progress_cb)
            if keep_parts:
                # 保留临时文件到同级目录（重命名避免冲突）
                video_tmp.replace(save_dir / f"{save_path.stem}.video.{video_stream.ext}")
                audio_tmp.replace(save_dir / f"{save_path.stem}.audio.{audio_stream.ext}")

        return DownloadResult(path=save_path, media_type="video", size=save_path.stat().st_size)

    def download_cover(
        self,
        bvid: str,
        dir: Optional[Path] = None,
        *,
        progress_cb: Optional[ProgressCallback] = None,
        filename: Optional[str] = None,
    ) -> DownloadResult:
        """下载视频封面。文件名为 `[标题](BV号).jpg/png`。

        :param bvid: BV号
        :param dir: 保存目录。None 时使用默认下载目录
        :param progress_cb: 进度回调 (downloaded, total)
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

        content = self.session.get_raw(info.pic)
        save_path.write_bytes(content)
        if progress_cb:
            progress_cb(len(content), len(content))
        return DownloadResult(path=save_path, media_type="cover", size=len(content))
