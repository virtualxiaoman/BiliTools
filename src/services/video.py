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
import time
import random
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Union

from src.api.auth import get_wbi
from src.api.errors import (
    BiliAPIError,
    BiliForbiddenError,
    BiliRiskError,
    FFmpegNotFoundError,
)
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
from src.util.filename import (
    build_download_filename,
    build_multi_page_filename,
    resolve_save_path,
)
from src.util.progress import BatchProgress, ParallelBatchProgress
from src.util.risk_gate import RiskGate

logger = logging.getLogger(__name__)

_ALLOWED_MEDIA_TYPES = {"video", "audio", "video_with_audio", "cover"}


class _FileCounter:
    """线程安全的文件序号分配：并发下载时每个视频（稿件）预先占号，保证进度序号不重叠。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._val = 0

    def reserve(self, n: int) -> int:
        """预留 n 个文件序号，返回这批的起始值（0 起，配合 _download_episode 的 ++ 后为 1 起显示）。"""
        with self._lock:
            start = self._val
            self._val += max(n, 0)
            return start


def _parallel_run(items, fn, threads: int, on_complete: Optional[Callable[[int, Any], None]] = None) -> list:
    """并发执行 fn(item, idx)，返回按输入顺序排列的结果列表。

    ``on_complete`` 会在每个任务实际完成后立即调用，调用顺序是任务完成顺序，
    而不是输入顺序。结果列表本身仍按输入顺序排列，避免改变下载接口的返回值语义。

    :param items: 输入列表
    :param fn: fn(item, index) -> result；异常会上抛（线程池退出时会等其余任务跑完）
    :param threads: 并发线程数
    :param on_complete: 可选的完成回调，签名为 ``(index, result)``
    """
    results: list = [None] * len(items)
    if len(items) <= 1 or threads <= 1:
        for i, item in enumerate(items):
            result = fn(item, i)
            results[i] = result
            if on_complete is not None:
                on_complete(i, result)
        return results
    with ThreadPoolExecutor(max_workers=threads) as ex:
        future_to_idx = {ex.submit(fn, item, i): i for i, item in enumerate(items)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            result = future.result()
            results[idx] = result
            if on_complete is not None:
                on_complete(idx, result)
    return results


def _valid_image_bytes(data: bytes) -> bool:
    return (data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG\r\n\x1a\n")
            or data.startswith((b"GIF87a", b"GIF89a"))
            or data.startswith(b"RIFF") and data[8:12] == b"WEBP")


class VideoService:
    """B 站视频的获取与下载服务。"""

    def __init__(self, session: Optional[BiliSession] = None, default_dir: Path = VIDEO_OUTPUT_DIR,
                 cancel_event: Optional[threading.Event] = None):
        """
        :param session: BiliSession 实例，None 时创建（使用默认 cookie）
        :param default_dir: 默认下载目录，调用下载方法未指定 dir 时使用
        """
        self._owns_session = session is None
        self.session = session if session is not None else BiliSession()
        self.default_dir = Path(default_dir)
        self.cancel_event = cancel_event

    # ---- 视频信息 ----

    def fetch_info(self, bvid: str) -> VideoInfo:
        """获取视频基本信息（标题/统计/作者等），并填充 cid。

        :param bvid: BV号
        :return: VideoInfo
        """
        # VIEW 返回原始 data；模型层在这里完成字段兼容、owner/stat/pages/season
        # 的组装，后续下载流程只依赖 VideoInfo，不再直接读取接口字典。
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
        """获取并严格校验视频 DASH 播放流。"""
        params = {
            "bvid": bvid, "cid": cid, "qn": 120, "fnver": 0, "fnval": fnval,
            "fourk": 1, "platform": "pc", "high_quality": 1,
        }
        get_wbi(params)
        data = self.session.get(VideoUrls.PLAY, params=params)
        if not isinstance(data, dict):
            raise BiliAPIError("播放流响应 data 类型错误")
        dash = data.get("dash")
        if not isinstance(dash, dict):
            raise BiliAPIError("播放流响应缺少 dash 数据")
        raw_videos = dash.get("video")
        raw_audios = dash.get("audio")
        if not isinstance(raw_videos, list) or not isinstance(raw_audios, list):
            raise BiliAPIError("播放流响应的 video/audio 字段类型错误")
        videos = []
        for value in raw_videos:
            if not isinstance(value, dict) or not isinstance(value.get("baseUrl"), str) or not value["baseUrl"]:
                continue
            videos.append(VideoStream(url=value["baseUrl"], codecs=value.get("codecs", ""),
                                      width=value.get("width", 0), height=value.get("height", 0),
                                      quality=value.get("id", 0), frame_rate=value.get("frameRate", ""),
                                      size=value.get("size", 0)))
        audios = []
        for value in raw_audios:
            if not isinstance(value, dict) or not isinstance(value.get("baseUrl"), str) or not value["baseUrl"]:
                continue
            audios.append(AudioStream(url=value["baseUrl"], codecs=value.get("codecs", ""),
                                      bandwidth=value.get("bandwidth", 0), size=value.get("size", 0)))
        if not videos or not audios:
            raise BiliAPIError("播放流响应不含可用的视频或音频流")
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
        # 每种下载（视频、音频、合成、封面）都先复用同一条信息链：
        # BV -> VIEW -> VideoInfo -> 目标分P/cid -> PLAY -> DASH 流。
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

    def _is_video_unavailable_error(self, exc: Exception) -> bool:
        """视频不存在或不可见（-404 不存在 / 62002 稿件不可见），批量下载时跳过该视频即可。"""
        return isinstance(exc, BiliAPIError) and exc.code in (-404, 62002)

    def _is_risk_control_error(self, exc: Exception) -> bool:
        """是否触发风控（-412 触发风控 / -403 被拒绝访问），这类错误稍作等待后重试通常可恢复。"""
        return isinstance(exc, (BiliRiskError, BiliForbiddenError))

    def _execute_batch_download(
            self,
            bvid: str,
            action: Callable[[], Any],
            *,
            label: str = "",
            retries: int = 3,
            risk_gate: Optional[RiskGate] = None,
    ) -> Any:
        """执行批量下载中单个视频（稿件）的下载动作，统一处理异常。

        - 视频不可见（-404 不存在 / 62002 稿件不可见）：记录日志并返回 None（跳过）；
        - 触发风控（-412 / -403）：有 risk_gate 时标记风控事件（由 gate 让**所有线程**
          在下一次获取信息前各自随机暂停），无 gate 时保持原有本地退避重试；
        - 其余异常：原样抛出。

        :param bvid: 视频BV号（仅用于日志）
        :param action: 无参可调用对象，完成该视频（稿件）的下载
        :param label: 批量任务描述（收藏夹/合集/UP主名称），仅用于日志
        :param retries: 触发风控后的最大重试次数
        :param risk_gate: 并发下载时的风控协调器；None 表示顺序下载（本地退避）
        :return: action 的返回值；视频不可见被跳过时返回 None
        """
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            if risk_gate is not None:
                # 风控后所有线程在下一次获取信息前暂停（每个线程暂停时长单独计算）
                risk_gate.pause_before_fetch()
            try:
                return action()
            except Exception as e:
                if self._is_video_unavailable_error(e):
                    logger.warning("视频 %s 不可见，跳过（%s）。", bvid, label)
                    return None
                if self._is_risk_control_error(e):
                    last_error = e
                    if risk_gate is not None:
                        logger.warning(
                            "视频 %s 触发风控（第 %d/%d 次尝试），通知所有线程暂停（%s）。",
                            bvid, attempt + 1, retries + 1, label)
                        risk_gate.mark_risk()
                    else:
                        wait = random.uniform(3, 8) * (attempt + 1)
                        logger.warning(
                            "视频 %s 触发风控（第 %d/%d 次尝试），等待 %.1fs 后重试（%s）。",
                            bvid, attempt + 1, retries + 1, wait, label)
                        time.sleep(wait)
                    continue
                raise
        logger.error("视频 %s 连续 %d 次触发风控，已放弃（%s）。", bvid, retries + 1, label)
        if last_error is not None:
            raise last_error
        raise BiliRiskError(f"视频 {bvid} 触发风控，已放弃（{label}）。")

    def _report_bvid_download(self, bvid: str, new_results: list, download_count: int, index: int, total: int) -> int:
        """报告单个视频的缓存命中/下载情况，并做防风控节流，返回累计的未命中缓存下载次数。

        - 全部命中本地缓存：提示跳过网络请求，不节流；
        - 有新下载：提示文件数，短停 0.3s；每累计 10 个未命中缓存的视频再随机休息 1~3s，降低风控风险。
        """
        all_cached = bool(new_results) and all(result.cached for result in new_results)
        if all_cached:
            print(f"{bvid}：命中缓存")
        else:
            print(f"{bvid}：下载 {len(new_results)} 个文件")
            download_count += 1
            time.sleep(0.3)  # 避免风控
            if download_count % 10 == 0:
                time.sleep(random.uniform(1, 3))  # 每10个未命中缓存的视频随机休息1~3秒，降低风控风险
        print(f"已下载 {index}/{total} 个视频")
        return download_count

    @staticmethod
    def _cache_roots(
            save_dir: Path,
            cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None,
    ) -> list[Path]:
        """返回缓存查验目录，始终把当前下载目录放在第一位并去重。"""
        roots = []
        extra_dirs = [] if cache_dirs is None else [cache_dirs] if isinstance(cache_dirs, (str, Path)) else cache_dirs
        for value in [save_dir, *extra_dirs]:
            if value is None:
                continue
            path = Path(value).expanduser()
            if path not in roots:
                roots.append(path)
        return roots

    def _find_downloaded_file(self, bvid: str, extensions: set[str],
                              page: Optional[int] = None, root: Optional[Path] = None,
                              roots: Optional[Iterable[Path]] = None) -> Optional[Path]:
        search_roots = list(roots) if roots is not None else [root or self.default_dir]
        extensions = {ext.lower().lstrip(".") for ext in extensions}
        page_tag = f"-p{page:02d}" if page is not None and page > 1 else None
        for value in search_roots:
            if value is None:
                continue
            search_root = Path(value).expanduser()
            if not search_root.is_dir():
                continue
            for path in search_root.rglob("*"):
                if (not path.is_file() or path.name.endswith((".part", ".tmp"))
                        or path.stat().st_size <= 0):
                    continue
                if bvid.casefold() not in path.stem.casefold():
                    continue
                if path.suffix.casefold().lstrip(".") not in extensions:
                    continue
                if page_tag is not None and page_tag not in path.stem.casefold():
                    continue
                return path
        return None

    def download_video(
            self, bvid: str, dir: Optional[Path] = None, *, page: int = 1,
            quality: VideoQuality = VideoQuality.HD4K, progress_cb: Optional[ProgressCallback] = None,
            progress: Optional[BatchProgress] = None, filename: Optional[str] = None,
            cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None, force: bool = False,
    ) -> DownloadResult:
        save_dir = Path(dir) if dir is not None else self.default_dir
        existing = None if force else self._find_downloaded_file(
            bvid, {"mp4", "flv", "m4s"}, page=page, roots=self._cache_roots(save_dir, cache_dirs))
        if existing is not None:
            return DownloadResult(path=existing, media_type="video", size=existing.stat().st_size, cached=True)
        info, dash = self._fetch_streams(bvid, page)
        stream = dash.pick_video(quality)
        if stream is None:
            raise ValueError(f"视频 {bvid} 第 {page} 分P 没有可用的视频流。")
        safe_name = filename or self._default_filename(info, bvid, page, stream.ext)
        save_path = resolve_save_path(save_dir, safe_name)
        if save_path.is_file() and save_path.stat().st_size > 0 and not force:
            return DownloadResult(path=save_path, media_type="video", size=save_path.stat().st_size, cached=True)
        progress, auto = self._auto_progress(safe_name, progress, progress_cb)
        try:
            if progress:
                picked = VideoQuality.from_qn(stream.quality)
                if picked is not None:
                    progress.set_quality(picked)
            size = download_stream(stream.url, save_path, self.session.session.headers,
                                   progress_cb=progress.make_stream_callback() if progress else progress_cb,
                                   overwrite=force, cancel_event=getattr(self, "cancel_event", None))
            return DownloadResult(path=save_path, media_type="video", size=size)
        finally:
            if auto:
                progress.finish()

    def download_audio(
            self, bvid: str, dir: Optional[Path] = None, *, page: int = 1,
            progress_cb: Optional[ProgressCallback] = None, progress: Optional[BatchProgress] = None,
            filename: Optional[str] = None, cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None,
            force: bool = False,
    ) -> DownloadResult:
        save_dir = Path(dir) if dir is not None else self.default_dir
        existing = None if force else self._find_downloaded_file(
            bvid, {"m4a", "mp3", "flac", "aac"}, page=page, roots=self._cache_roots(save_dir, cache_dirs))
        if existing is not None:
            return DownloadResult(path=existing, media_type="audio", size=existing.stat().st_size, cached=True)
        info, dash = self._fetch_streams(bvid, page)
        stream = dash.best_audio()
        if stream is None:
            raise ValueError(f"视频 {bvid} 第 {page} 分P 没有可用的音频流。")
        safe_name = filename or self._default_filename(info, bvid, page, stream.ext)
        save_path = resolve_save_path(save_dir, safe_name)
        if save_path.is_file() and save_path.stat().st_size > 0 and not force:
            return DownloadResult(path=save_path, media_type="audio", size=save_path.stat().st_size, cached=True)
        progress, auto = self._auto_progress(safe_name, progress, progress_cb)
        try:
            size = download_stream(stream.url, save_path, self.session.session.headers,
                                   progress_cb=progress.make_stream_callback() if progress else progress_cb,
                                   overwrite=force, cancel_event=getattr(self, "cancel_event", None))
            return DownloadResult(path=save_path, media_type="audio", size=size)
        finally:
            if auto:
                progress.finish()

    def download_video_with_audio(
            self, bvid: str, dir: Optional[Path] = None, *, page: int = 1,
            quality: VideoQuality = VideoQuality.HD4K, keep_parts: bool = False,
            progress_cb: Optional[ProgressCallback] = None, progress: Optional[BatchProgress] = None,
            filename: Optional[str] = None, cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None,
            force: bool = False,
    ) -> DownloadResult:
        import tempfile
        save_dir = Path(dir) if dir is not None else self.default_dir
        existing = None if force else self._find_downloaded_file(
            bvid, {"mp4", "flv", "m4s"}, page=page, roots=self._cache_roots(save_dir, cache_dirs))
        if existing is not None:
            return DownloadResult(path=existing, media_type="video", size=existing.stat().st_size, cached=True)
        if not ffmpeg_available():
            raise FFmpegNotFoundError("未检测到 ffmpeg，且未安装 imageio-ffmpeg 库，无法进行音视频合成。")
        info, dash = self._fetch_streams(bvid, page)
        video_stream, audio_stream = dash.pick_video(quality), dash.best_audio()
        if video_stream is None or audio_stream is None:
            raise ValueError(f"视频 {bvid} 第 {page} 分P 的视频流或音频流不可用，无法合成。")
        safe_name = filename or self._default_filename(info, bvid, page, "mp4")
        save_path = resolve_save_path(save_dir, safe_name)
        if save_path.is_file() and save_path.stat().st_size > 0 and not force:
            return DownloadResult(path=save_path, media_type="video", size=save_path.stat().st_size, cached=True)
        progress, auto = self._auto_progress(safe_name, progress, progress_cb)
        try:
            if progress:
                picked = VideoQuality.from_qn(video_stream.quality)
                if picked is not None:
                    progress.set_quality(picked)
            with tempfile.TemporaryDirectory(prefix="bilitools_", dir=save_dir) as tmp:
                tmp_dir = Path(tmp)
                video_tmp = tmp_dir / f"video.{video_stream.ext}"
                audio_tmp = tmp_dir / f"audio.{audio_stream.ext}"
                state = {"id": 0, "last": 0}

                def cb(done: int, total: Optional[int]) -> None:
                    if progress:
                        delta = max(0, done - state["last"])
                        progress.add(delta, total, stream_id=state["id"])
                        state["last"] = done
                    elif progress_cb:
                        progress_cb(done, total)

                download_stream(video_stream.url, video_tmp, self.session.session.headers,
                                progress_cb=cb, cancel_event=getattr(self, "cancel_event", None))
                if progress:
                    progress.status("视频流下载完成，正在下载音频流...")
                    state["id"], state["last"] = 1, 0
                download_stream(audio_stream.url, audio_tmp, self.session.session.headers,
                                progress_cb=cb, cancel_event=getattr(self, "cancel_event", None))
                if progress:
                    progress.status("正在用 ffmpeg 合成音视频...")
                merge_video_audio(video_tmp, audio_tmp, save_path, progress_cb=progress_cb,
                                  cancel_event=getattr(self, "cancel_event", None))
                if keep_parts:
                    video_tmp.replace(save_dir / f"{save_path.stem}.video.{video_stream.ext}")
                    audio_tmp.replace(save_dir / f"{save_path.stem}.audio.{audio_stream.ext}")
            return DownloadResult(path=save_path, media_type="video", size=save_path.stat().st_size)
        finally:
            if auto:
                progress.finish()

    def download_cover(
            self, bvid: str, dir: Optional[Path] = None, *, progress_cb: Optional[ProgressCallback] = None,
            progress: Optional[BatchProgress] = None, filename: Optional[str] = None,
            cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None, force: bool = False,
    ) -> DownloadResult:
        save_dir = Path(dir) if dir is not None else self.default_dir
        existing = None if force else self._find_downloaded_file(
            bvid, {"jpg", "jpeg", "png", "webp"}, roots=self._cache_roots(save_dir, cache_dirs))
        if existing is not None:
            return DownloadResult(path=existing, media_type="cover", size=existing.stat().st_size, cached=True)
        info = self.fetch_info(bvid)
        if not info.pic:
            raise ValueError(f"视频 {bvid} 的封面地址获取失败。")
        ext = "png" if info.pic.lower().split("?", 1)[0].endswith(".png") else "jpg"
        safe_name = filename or build_download_filename(info.title, bvid, ext)
        save_path = resolve_save_path(save_dir, safe_name)
        if save_path.is_file() and save_path.stat().st_size > 0 and not force:
            return DownloadResult(path=save_path, media_type="cover", size=save_path.stat().st_size, cached=True)
        progress, auto = self._auto_progress(safe_name, progress, progress_cb)
        try:
            content = self.session.get_raw(info.pic, max_bytes=16 * 1024 * 1024)
            if not _valid_image_bytes(content):
                raise ValueError("封面响应不是受支持的图片格式")
            part = save_path.with_name(save_path.name + ".part")
            part.write_bytes(content)
            part.replace(save_path)
            if progress:
                progress.update(len(content), len(content))
            elif progress_cb:
                progress_cb(len(content), len(content))
            return DownloadResult(path=save_path, media_type="cover", size=len(content))
        finally:
            if auto:
                progress.finish()

    def download_all_pages(
            self, bvid: str, dir: Optional[Path] = None, *,
            quality: VideoQuality = VideoQuality.HD4K, media_type: str = "video_with_audio",
            progress_cb: Optional[ProgressCallback] = None, progress: Optional[BatchProgress] = None,
            cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None, force: bool = False,
    ) -> list:
        if media_type not in _ALLOWED_MEDIA_TYPES:
            raise ValueError(f"不支持的媒体类型：{media_type!r}，允许值：{sorted(_ALLOWED_MEDIA_TYPES)}")
        info = self.fetch_info(bvid)
        if not info.pages:
            raise ValueError(f"视频 {bvid} 没有分P信息，无法批量下载。")
        # 封面属于稿件级资源，没有 page-specific URL；多P只下载一次，避免重复覆盖同一个文件。
        pages = info.pages if media_type != "cover" else info.pages[:1]
        progress = progress or BatchProgress(n=len(pages), label=f"视频 {bvid}")
        results = []
        for i, page_obj in enumerate(pages, 1):
            display_ext = {"video": "mp4", "audio": "m4a", "cover": "jpg"}.get(media_type, "mp4")
            display_name = self._default_filename(info, bvid, page_obj.page, display_ext)
            progress.start(i, display_name)
            try:
                logger.debug("正在下载 %s 第 %d/%d 分P：%s", bvid, page_obj.page, len(pages), page_obj.part)
                if media_type == "video":
                    result = self.download_video(bvid, dir, page=page_obj.page, quality=quality,
                                                 progress_cb=progress_cb, progress=progress,
                                                 cache_dirs=cache_dirs, force=force)
                elif media_type == "audio":
                    result = self.download_audio(bvid, dir, page=page_obj.page,
                                                 progress_cb=progress_cb, progress=progress,
                                                 cache_dirs=cache_dirs, force=force)
                elif media_type == "cover":
                    result = self.download_cover(bvid, dir, progress_cb=progress_cb, progress=progress,
                                                 cache_dirs=cache_dirs, force=force)
                else:
                    result = self.download_video_with_audio(bvid, dir, page=page_obj.page, quality=quality,
                                                            progress_cb=progress_cb, progress=progress,
                                                            cache_dirs=cache_dirs, force=force)
                results.append(result)
            finally:
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
                data = ArchiveService(self.session).get_season_by_sid(season_id, mid)
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

    def _download_episode(
            self, episode: VideoSeasonEpisode, save_dir: Path, *, media_type: str,
            quality: VideoQuality, file_idx: int, progress: Optional[BatchProgress] = None,
            progress_cb: Optional[ProgressCallback] = None,
            cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None, force: bool = False,
    ) -> tuple[list, int]:
        if media_type not in _ALLOWED_MEDIA_TYPES:
            raise ValueError(f"不支持的媒体类型：{media_type!r}")
        info = self.fetch_info(episode.bvid)
        new_results = []
        page_objs = episode.pages if episode.is_multi_page and media_type != "cover" else [
            VideoPage(page=1, cid=info.cid or 0, part=info.title)]
        for page_obj in page_objs:
            file_idx += 1
            display_ext = {"video": "mp4", "audio": "m4a", "cover": "jpg"}.get(media_type, "mp4")
            display_name = self._default_filename(info, episode.bvid, page_obj.page, display_ext)
            progress.start(file_idx, display_name)
            try:
                if media_type == "video":
                    result = self.download_video(episode.bvid, save_dir, page=page_obj.page, quality=quality,
                                                 progress_cb=progress_cb, progress=progress, cache_dirs=cache_dirs,
                                                 force=force)
                elif media_type == "audio":
                    result = self.download_audio(episode.bvid, save_dir, page=page_obj.page,
                                                 progress_cb=progress_cb, progress=progress, cache_dirs=cache_dirs,
                                                 force=force)
                elif media_type == "cover":
                    result = self.download_cover(episode.bvid, save_dir, progress_cb=progress_cb, progress=progress,
                                                 cache_dirs=cache_dirs, force=force)
                else:
                    result = self.download_video_with_audio(episode.bvid, save_dir, page=page_obj.page, quality=quality,
                                                            progress_cb=progress_cb, progress=progress,
                                                            cache_dirs=cache_dirs, force=force)
                new_results.append(result)
            finally:
                progress.finish()
        return new_results, file_idx

    def _account_services(self, account_sessions=None, threads: int = 1) -> list:
        """为并发 worker 创建互不共享的 requests.Session。"""
        if account_sessions:
            return [VideoService(session=session, default_dir=self.default_dir,
                                 cancel_event=getattr(self, "cancel_event", None))
                    for session in account_sessions]
        if threads <= 1:
            return [self]
        # 测试 double 或外部自定义 session 没有 BiliSession 的配置快照时，
        # 无法安全复制；回退到调用方对象，保持兼容性。真实生产会话始终隔离。
        if not isinstance(self.session, BiliSession):
            return [self]
        services = []
        for _ in range(threads):
            session = BiliSession(cookie_path=self.session.cookie_path, referer=self.session.referer,
                                  max_retry=self.session.max_retry, timeout=self.session.timeout)
            service = VideoService(session=session, default_dir=self.default_dir,
                                   cancel_event=getattr(self, "cancel_event", None))
            service._owns_session = True
            services.append(service)
        return services

    @staticmethod
    def _close_owned_services(services: Optional[Iterable["VideoService"]]) -> None:
        """关闭并发期间由本服务创建的会话，不关闭调用方传入的会话。"""
        for service in services or ():
            if not getattr(service, "_owns_session", False):
                continue
            try:
                service.session.close()
            except Exception:
                logger.warning("关闭并发下载会话失败", exc_info=True)

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
            season: Optional[VideoSeason] = None,
            threads: int = 1,
            account_sessions: Optional[list] = None,
            cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None,
            force: bool = False,
    ) -> list:
        """下载整个合集。`bvid` 与 `season_id` 任选其一。

        - 传 `bvid`：从合集内任意一个视频进入，反查合集并下载全部稿件；
        - 传 `season_id`：按合集 sid 直接下载（如 sid=8683221 或 sid=1717000）。

        每个稿件若有多个分P，则逐P下载。文件保存到 `<dir>/<合集标题>/`。
        `threads > 1` 时多个稿件并发下载（需配合线程安全的 progress）；任一稿件触发
        风控时，所有线程在下一次获取信息前各自随机暂停。
        `account_sessions` 非空时，并发线程**均匀分摊到各账号**（任务按下标轮询账号），
        降低单个账号的风控风险。

        :param bvid: 合集内任意一个视频的BV号
        :param dir: 保存根目录。None 时使用默认下载目录
        :param season_id: 合集 sid
        :param mid: season_id 方式下合集所属用户UID，0 时尝试用当前登录用户
        :param quality: 目标清晰度（精确匹配，匹配不到回退到最高可用）
        :param media_type: 下载类型：video / audio / video_with_audio / cover
        :param progress_cb: 进度回调 (downloaded, total)
        :param progress: BatchProgress 进度显示；None 时自动创建（并发时创建线程安全版本）
        :param season: 可选：外部已获取的合集结构（VideoSeason）。传入时跳过内部重复反查
            （GUI 场景会先取合集用于进度总数，传回此处避免请求两次）；None 时内部自动获取
        :param threads: 并发下载线程数（>1 启用并发，需线程安全的 progress）
        :param account_sessions: 可选：多个账号的 BiliSession 列表，用于把并发任务均匀
            分摊到各账号（多账号降风控）；None 时全部任务使用当前账号
        :param cache_dirs: 额外缓存查验目录；当前保存目录始终自动加入且优先查验
        :param force: 是否忽略缓存并强制下载；同名目标文件覆盖
        :return: DownloadResult 列表
        :raises ValueError: 无法定位合集
        """
        if media_type not in _ALLOWED_MEDIA_TYPES:
            raise ValueError(f"不支持的媒体类型：{media_type!r}，允许值：{sorted(_ALLOWED_MEDIA_TYPES)}")
        if season is None:
            season = self.fetch_season(bvid, season_id, mid)
        if season is None or not season.episodes:
            loc = f"bvid={bvid}" if bvid else f"season_id={season_id}"
            raise ValueError(f"{loc} 无法定位到合集，请确认参数正确。")

        save_dir = (Path(dir) if dir is not None else self.default_dir) / season.title
        save_dir.mkdir(parents=True, exist_ok=True)

        # 计算总共要下载的文件数（多P稿件按分P数计），驱动进度
        file_count = sum(len(ep.pages) if ep.is_multi_page else 1 for ep in season.episodes)
        if progress is None:
            progress = (ParallelBatchProgress(n=file_count, label=f"合集「{season.title}」")
                        if threads > 1 else BatchProgress(n=file_count, label=f"合集「{season.title}」"))

        label = f"合集「{season.title}」"
        total = len(season.episodes)
        if threads > 1:
            services = self._account_services(account_sessions, threads)
            try:
                return self._download_season_parallel(
                    season, save_dir, quality=quality, media_type=media_type,
                    progress=progress, progress_cb=progress_cb, label=label, threads=threads,
                    services=services, cache_dirs=cache_dirs, force=force,
                )
            finally:
                self._close_owned_services(services)

        results = []
        download_count = 0
        file_idx = 0
        for i, episode in enumerate(season.episodes, 1):
            logger.info("合集「%s」下载：%s", season.title, episode.title)
            # 起始文件序号在闭包里固定：风控重试会重新执行整个动作，不能捕获到已更新的 file_idx
            outcome = self._execute_batch_download(
                episode.bvid,
                lambda ep=episode, start_idx=file_idx: self._download_episode(
                    ep, save_dir, media_type=media_type, quality=quality,
                    file_idx=start_idx, progress=progress, progress_cb=progress_cb,
                    cache_dirs=cache_dirs, force=force,
                ),
                label=label,
            )
            if outcome is None:
                continue  # 视频不可见：_execute_batch_download 已记录日志
            new_results, file_idx = outcome
            results.extend(new_results)
            download_count = self._report_bvid_download(
                episode.bvid, new_results, download_count, i, total,
            )
        return results

    def _download_season_parallel(self, season, save_dir, *, quality, media_type,
                                  progress, progress_cb, label, threads, services,
                                  cache_dirs=None, force=False) -> list:
        """合集并发下载：每个稿件一个线程，共享风控协调器；任务按下标轮询 services 分摊账号。"""
        gate = RiskGate()
        counter = _FileCounter()

        def _work(episode, i):
            svc = services[i % len(services)]
            num_pages = len(episode.pages) if episode.is_multi_page else 1
            start_idx = counter.reserve(num_pages)
            return svc._execute_batch_download(
                episode.bvid,
                lambda ep=episode, sidx=start_idx: svc._download_episode(
                    ep, save_dir, media_type=media_type, quality=quality,
                    file_idx=sidx, progress=progress, progress_cb=progress_cb,
                    cache_dirs=cache_dirs, force=force,
                ),
                label=label, risk_gate=gate,
            )

        completed_count = 0
        download_count = 0
        total = len(season.episodes)

        def _on_complete(index, outcome):
            """任务完成时立即输出视频级汇总日志。"""
            nonlocal completed_count, download_count
            completed_count += 1
            if outcome is None:
                return
            episode = season.episodes[index]
            new_results, _ = outcome
            download_count = self._report_bvid_download(
                episode.bvid, new_results, download_count, completed_count, total,
            )

        outcomes = _parallel_run(season.episodes, _work, threads, on_complete=_on_complete)
        # 下载结果仍按输入顺序返回；汇总日志已在每个任务完成时即时输出。
        results = []
        for outcome in outcomes:
            if outcome is not None:
                new_results, _ = outcome
                results.extend(new_results)
        return results

    # ---- 统一下载接口 ----

    def download(self, bvid: str, dir: Optional[Path] = None, *,
                 cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None, force: bool = False) -> list:
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
        # 统一入口只做“范围决策”：先查视频是否带合集结构，再把实际下载
        # 委托给已有的合集/全部分P流程，避免 GUI、CLI 各自复制判断逻辑。
        info = self.fetch_info(bvid)
        if info.season and info.season.episodes:
            # 属于合集：下载整个合集
            return self.download_season(bvid=bvid, dir=dir, quality=VideoQuality.HD4K,
                                        cache_dirs=cache_dirs, force=force)
        # 单视频（含多P）：下载全部分P
        return self.download_all_pages(bvid, dir, quality=VideoQuality.HD4K,
                                       cache_dirs=cache_dirs, force=force)

    def _download_bvid_collection(
            self,
            bvids: list,
            save_dir: Path,
            *,
            quality: VideoQuality,
            media_type: str,
            progress: BatchProgress,
            progress_cb: Optional[ProgressCallback],
            threads: int,
            account_sessions: Optional[list],
            cache_dirs: Optional[Union[Iterable[Path], Path, str]],
            force: bool,
            item_label: Callable[[str], str],
            on_skip: Optional[Callable[[str, int, int], None]] = None,
    ) -> list:
        """统一执行收藏夹、UP 主等 BV 列表批量下载。"""
        total = len(bvids)
        if threads > 1:
            gate = RiskGate()
            services = self._account_services(account_sessions, threads)

            def work(bvid, index):
                service = services[index % len(services)]
                return service._execute_batch_download(
                    bvid,
                    lambda current_bvid=bvid: service.download_all_pages(
                        current_bvid, save_dir, quality=quality, media_type=media_type,
                        progress=progress, progress_cb=progress_cb,
                        cache_dirs=cache_dirs, force=force,
                    ),
                    label=item_label(bvid), risk_gate=gate,
                )

            completed_count = 0
            download_count = 0

            def report_completion(index, outcome):
                nonlocal completed_count, download_count
                bvid = bvids[index]
                completed_count += 1
                if outcome is None:
                    if on_skip is not None:
                        on_skip(bvid, completed_count, total)
                    return
                download_count = self._report_bvid_download(
                    bvid, outcome, download_count, completed_count, total,
                )

            try:
                outcomes = _parallel_run(
                    bvids, work, threads, on_complete=report_completion,
                )
                results = []
                for outcome in outcomes:
                    if outcome is not None:
                        results.extend(outcome)
                return results
            finally:
                self._close_owned_services(services)

        results = []
        download_count = 0
        for index, bvid in enumerate(bvids, 1):
            logger.info("%s：%s", item_label(bvid), bvid)
            new_results = self._execute_batch_download(
                bvid,
                lambda current_bvid=bvid: self.download_all_pages(
                    current_bvid, save_dir, quality=quality, media_type=media_type,
                    progress=progress, progress_cb=progress_cb,
                    cache_dirs=cache_dirs, force=force,
                ),
                label=item_label(bvid),
            )
            if new_results is None:
                if on_skip is not None:
                    on_skip(bvid, index, total)
                continue
            results.extend(new_results)
            download_count = self._report_bvid_download(
                bvid, new_results, download_count, index, total,
            )
        return results

    def download_fav(
            self,
            fid: Optional[int] = None,
            dir: Optional[Path] = None,
            *,
            mode: str = "video",
            quality: VideoQuality = VideoQuality.HD4K,
            progress_cb: Optional[ProgressCallback] = None,
            progress: Optional[BatchProgress] = None,
            bvids: Optional[list] = None,
            threads: int = 1,
            account_sessions: Optional[list] = None,
            cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None,
            force: bool = False,
    ) -> list:
        """下载整个收藏夹的全部视频（有声音）或仅音频。

        逐个下载收藏夹内的视频，保存到 `<dir>/<收藏夹名称>/`（默认 `output/video/<收藏夹名称>/`）。
        每个视频若有分P则逐P下载。下载带进度显示（含清晰度标签）。
        `threads > 1` 时多个视频并发下载；任一视频触发风控时所有线程在下一次获取信息前各自随机暂停。
        `account_sessions` 非空时，并发任务**均匀分摊到各账号**（按下标轮询），降低单个账号风控风险。

        [使用方法]
            service = VideoService()
            service.download_fav(3953119978)
            # 仅下载音频（本地缓存听歌）
            service.download_fav(3953119978, mode="audio")

        :param fid: 收藏夹 media_id（int）
        :param dir: 保存根目录。None 时使用默认下载目录
        :param mode: video（下载视频+音频合成，默认）或 audio（仅下载音频流）
        :param quality: 目标清晰度（精确匹配，默认 HD4K 最高）
        :param progress_cb: 进度回调 (downloaded, total)
        :param progress: BatchProgress 进度显示（与 progress_cb 二选一，通常由 UI 传入以获取逐文件事件）
        :param bvids: 可选：外部已获取的收藏夹视频 BV 号列表。传入时跳过内部重复拉取
            （GUI 场景会先取列表用于进度总数，传回此处避免请求两次）；None 时内部自动获取
        :param threads: 并发下载线程数（>1 启用并发，需线程安全的 progress）
        :param account_sessions: 可选：多个账号的 BiliSession 列表，用于把并发任务均匀
            分摊到各账号（多账号降风控）；None 时全部任务使用当前账号
        :param cache_dirs: 额外缓存查验目录；当前保存目录始终自动加入且优先查验
        :param force: 是否忽略缓存并强制下载；同名目标文件覆盖
        :return: DownloadResult 列表
        """
        from src.services.fav import FavService

        # 收藏夹链路：media_id -> 收藏夹详情（决定目录名）-> BV 列表 ->
        # 对每个 BV 复用普通视频下载流程；GUI 传入 bvids 时可避免重复拉列表。
        fav = FavService(self.session)
        info = fav.get_fav_info(fid)
        if bvids is None:
            bvids = fav.get_fav_bv(fid)
        if not bvids:
            raise ValueError(f"收藏夹「{info.title}」没有视频。")

        save_dir = (Path(dir) if dir is not None else self.default_dir) / info.title
        save_dir.mkdir(parents=True, exist_ok=True)

        media_type = "audio" if mode == "audio" else "video_with_audio"
        label = f"收藏夹「{info.title}」"
        total = len(bvids)
        if progress is None:
            progress = (ParallelBatchProgress(n=total, label=label)
                        if threads > 1 else BatchProgress(n=total, label=label))

        return self._download_bvid_collection(
            bvids, save_dir, quality=quality, media_type=media_type,
            progress=progress, progress_cb=progress_cb, threads=threads,
            account_sessions=account_sessions, cache_dirs=cache_dirs, force=force,
            item_label=lambda bvid: label,
            on_skip=lambda bvid, index, count: print(
                f"跳过不可见视频 {bvid}，进度 {index}/{count}"
            ),
        )

    # ---- UP主空间 ----

    def _resolve_mid(self, mid: Optional[int]) -> int:
        """后端只接收规范 mid（int 或数字字符串），不接受 URL。

        链接解析统一由前端（frontend.pyside6.utils）归一化后再传入。
        """
        if mid is None:
            raise ValueError("需要提供 mid")
        s = str(mid).strip()
        if not s.isdigit():
            raise ValueError(f"mid 必须是纯数字，收到：{mid}")
        return int(s)

    def list_up_videos(self, mid: Optional[int] = None, ps: int = 30) -> list:
        """获取某个 UP 主空间的全部视频 BV 号列表（分页翻到底）。

        [使用方法]:
            service = VideoService()
            bvs = service.list_up_videos(249056021)

        :param mid: UP主 mid（int）
        :param ps: 每页数量（最大 50）
        :return: 视频bv号列表
        """
        from src.api.auth import get_wbi
        from src.urls.user_urls import UserUrls
        import time
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
            time.sleep(0.3)  # 避免风控
        return bvids

    def download_up(
            self,
            mid: Optional[int] = None,
            dir: Optional[Path] = None,
            *,
            mode: str = "video",
            quality: VideoQuality = VideoQuality.HD4K,
            progress_cb: Optional[ProgressCallback] = None,
            progress: Optional[BatchProgress] = None,
            bvids: Optional[list] = None,
            threads: int = 1,
            account_sessions: Optional[list] = None,
            cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None,
            force: bool = False,
    ) -> list:
        """下载某个 UP 主空间的全部视频（有声音）或仅音频。

        逐个下载该 UP 主的所有投稿，保存到 `<dir>/<UP主昵称>/`（默认 `output/video/<昵称>/`）。
        每个视频若有分P则逐P下载，带进度显示。
        `threads > 1` 时多个视频并发下载；任一视频触发风控时所有线程在下一次获取信息前各自随机暂停。
        `account_sessions` 非空时，并发任务**均匀分摊到各账号**（按下标轮询），降低单个账号风控风险。

        [使用方法]
            service = VideoService()
            service.download_up(249056021)
            # 仅下载音频
            service.download_up(249056021, mode="audio")

        :param mid: UP主 mid（int）
        :param dir: 保存根目录。None 时使用默认下载目录
        :param mode: video（下载视频+音频合成，默认）或 audio（仅下载音频流）
        :param quality: 目标清晰度（精确匹配，默认 HD4K 最高）
        :param progress_cb: 进度回调 (downloaded, total)
        :param progress: BatchProgress 进度显示（与 progress_cb 二选一，通常由 UI 传入以获取逐文件事件）
        :param bvids: 可选：外部已获取的 UP 主视频 BV 号列表。传入时跳过内部重复翻页拉取
            （GUI 场景会先取列表用于进度总数，传回此处避免请求两次）；None 时内部自动获取
        :param threads: 并发下载线程数（>1 启用并发，需线程安全的 progress）
        :param account_sessions: 可选：多个账号的 BiliSession 列表，用于把并发任务均匀
            分摊到各账号（多账号降风控）；None 时全部任务使用当前账号
        :param cache_dirs: 额外缓存查验目录；当前保存目录始终自动加入且优先查验
        :param force: 是否忽略缓存并强制下载；同名目标文件覆盖
        :return: DownloadResult 列表
        """
        from src.services.user import UserService

        # UP 主链路：规范化 mid -> 空间投稿分页得到 BV 列表 -> 查询昵称作为
        # 输出目录 -> 每个 BV 进入 download_all_pages；列表可由 GUI 预取后传入。
        mid = self._resolve_mid(mid)
        if bvids is None:
            bvids = self.list_up_videos(mid)
        if not bvids:
            raise ValueError(f"UP主 {mid} 没有视频。")

        up_name = UserService(self.session).get_name(mid) or f"up_{mid}"
        save_dir = (Path(dir) if dir is not None else self.default_dir) / up_name
        save_dir.mkdir(parents=True, exist_ok=True)

        media_type = "audio" if mode == "audio" else "video_with_audio"
        label = f"UP主「{up_name}」"
        total = len(bvids)
        if progress is None:
            progress = (ParallelBatchProgress(n=total, label=label)
                        if threads > 1 else BatchProgress(n=total, label=label))

        return self._download_bvid_collection(
            bvids, save_dir, quality=quality, media_type=media_type,
            progress=progress, progress_cb=progress_cb, threads=threads,
            account_sessions=account_sessions, cache_dirs=cache_dirs, force=force,
            item_label=lambda bvid: label,
            on_skip=lambda bvid, index, count: logger.warning(
                "视频 %s 不可见，跳过。", bvid
            ),
        )
