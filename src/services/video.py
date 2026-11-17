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

# todo: BV1MyHHzEECq应该因为空格无法下载。

import time
import random
import logging
import re
import threading
import zlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Union

from src.api.auth import get_wbi
from src.api.errors import (
    VIDEO_UNAVAILABLE_REASONS,
    BiliAPIError,
    BiliAuthError,
    BiliForbiddenError,
    BiliRiskError,
    DownloadCancelled,
    DownloadError,
    FFmpegNotFoundError,
    VideoChargingError,
    VideoPreviewOnlyError,
)
from src.api.session import BiliSession
from src.config.constants import DASH_FNVAL
from src.config.path import VIDEO_OUTPUT_DIR
from src.models.download_model import (
    AudioStream,
    DashStreams,
    DownloadResult,
    ProgressiveStream,
    VideoQuality,
    VideoStream,
)
from src.models.video_model import (
    VideoAISummary,
    VideoInfo,
    VideoPage,
    VideoSeason,
    VideoSeasonEpisode,
)
from src.services.account_capability import (
    AccountCapability,
    AccountPermissionCache,
    capability_for,
    capability_matches_session,
    same_account,
)
from src.services.archive import ArchiveService
from src.urls.video_urls import VideoUrls
from src.util.downloader import (
    ProgressCallback,
    download_stream,
    extract_audio,
    ffmpeg_available,
    merge_video_audio,
)
from src.util.filename import (
    build_download_filename,
    build_multi_page_filename,
    resolve_save_path,
    sanitize_filename,
)
from src.util.parallel import parallel_run
from src.util.progress import BatchProgress, ParallelBatchProgress
from src.util.risk_gate import RiskGate

logger = logging.getLogger(__name__)

_ALLOWED_MEDIA_TYPES = {"video", "audio", "video_with_audio", "cover", "danmaku"}

# 批量下载里“可重试的失败”标记：既不是成功结果，也不是永久跳过（None）。
_RETRY_OUTCOME = object()

# 多P文件名里的分P标签：`[标题]-P07-[分P标题](BV号).mp4`
_PAGE_TAG_RE = re.compile(r"-p\d{2,3}(?=[-(])")


def _has_page_tag(stem: str, page: int) -> bool:
    """文件名里是否有该分P的标签（兼容分P标题为空的情况）。"""
    return bool(re.search(rf"-p{page:02d}(?=[-(])", stem))


@dataclass
class _RetryPages:
    """批量队列里的“待重试分P”：下载队列和缓存都以分P为最小单位。"""

    bvid: str
    pages: list = field(default_factory=list)
    results: list = field(default_factory=list)


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


def _valid_image_bytes(data: bytes) -> bool:
    return (data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG\r\n\x1a\n")
            or data.startswith((b"GIF87a", b"GIF89a"))
            or data.startswith(b"RIFF") and data[8:12] == b"WEBP")


def _best_quality(dash: DashStreams) -> int:
    """播放流里可用的最高清晰度（qn）；直出流取接口返回的 quality。"""
    if dash.progressive is not None:
        return int(dash.progressive.quality or 0)
    stream = dash.best_video()
    return int(stream.quality) if stream is not None else 0


_AUDIO_KIND_LABELS = {"dolby": "杜比全景声", "flac": "无损 FLAC", "aac": "AAC"}


def _audio_label(stream: AudioStream) -> str:
    return _AUDIO_KIND_LABELS.get(stream.kind, stream.codecs or "音频")


def _audio_output_ext(stream: AudioStream) -> str:
    """纯音频下载的最终扩展名：杜比用 mka、无损用 flac，AAC 直接 m4a。"""
    if stream.kind == "flac":
        return "flac"
    if stream.kind == "dolby":
        return "mka"  # E-AC-3 不能放进 m4a 容器，Matroska 可容纳
    return stream.ext


class VideoService:
    """B 站视频的获取与下载服务。"""

    def __init__(self, session: Optional[BiliSession] = None, default_dir: Path = VIDEO_OUTPUT_DIR,
                 cancel_event: Optional[threading.Event] = None,
                 permission_accounts: Optional[list[AccountCapability]] = None,
                 permission_cache: Optional[AccountPermissionCache] = None,
                 quality_cap: Optional[VideoQuality] = None,
                 cap_non_vip_quality: Optional[VideoQuality] = None):
        """
        :param session: BiliSession 实例，None 时创建（使用默认 cookie）
        :param default_dir: 默认下载目录，调用下载方法未指定 dir 时使用
        :param permission_accounts: 权限换号候选账号（含会员能力），空列表时不做换号
        :param permission_cache: 一次任务内共享的权限结论缓存（多线程/临时会话共用）
        :param quality_cap: 本会话允许下载的最高清晰度（非会员账号分流上限）
        :param cap_non_vip_quality: 为本服务创建的并发子服务设置非会员清晰度上限
        """
        self._owns_session = session is None
        self.session = session if session is not None else BiliSession()
        self.default_dir = Path(default_dir)
        self.cancel_event = cancel_event
        self.permission_accounts = list(permission_accounts or [])
        self.permission_cache = permission_cache if permission_cache is not None else AccountPermissionCache()
        self.quality_cap = quality_cap
        self.cap_non_vip_quality = cap_non_vip_quality
        if self.quality_cap is None and cap_non_vip_quality is not None:
            own = capability_for(self.session, self._permission_accounts_ref())
            if own is not None and own.is_vip is False:
                self.quality_cap = cap_non_vip_quality

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

    def fetch_ai_summary(
        self,
        bvid: str = "",
        aid: int = 0,
        cid: Optional[int] = None,
        up_mid: Optional[int] = None,
    ) -> VideoAISummary:
        """获取视频 AI 总结。

        ``cid`` 是必需的接口参数；未传入时会先请求视频信息自动取首个
        分 P 的 cid。``up_mid`` 是可选参数，未传入时会尽量从视频信息中
        自动补全。视频标识支持 BV 号或 AV 号，二者只能传一个。

        :param bvid: 视频 BV 号，与 ``aid`` 二选一
        :param aid: 视频 AV 号，与 ``bvid`` 二选一
        :param cid: 分 P cid；默认使用首个分 P
        :param up_mid: UP 主 mid，可选
        :return: :class:`VideoAISummary`
        """
        if isinstance(aid, bool) or (not bvid and not aid):
            raise ValueError("bvid 和 aid 必须二选一")
        if bvid and aid:
            raise ValueError("bvid 和 aid 不能同时传入")
        if not bvid:
            try:
                aid = int(aid)
            except (TypeError, ValueError) as exc:
                raise ValueError("aid 必须是正整数") from exc
            if aid <= 0:
                raise ValueError("aid 必须是正整数")

        if cid is not None:
            try:
                cid = int(cid)
            except (TypeError, ValueError) as exc:
                raise ValueError("cid 必须是正整数") from exc
            if cid <= 0:
                raise ValueError("cid 必须是正整数")
        if up_mid is not None:
            try:
                up_mid = int(up_mid)
            except (TypeError, ValueError) as exc:
                raise ValueError("up_mid 必须是正整数") from exc
            if up_mid <= 0:
                raise ValueError("up_mid 必须是正整数")

        # cid 缺失时需要查询 view；查询 view 的同时可补全可选 up_mid。
        if cid is None:
            view_params = {"bvid": bvid} if bvid else {"aid": int(aid)}
            info = VideoInfo.from_view_json(
                self.session.get(VideoUrls.VIEW, params=view_params)
            )
            if cid is None:
                cid = info.cid
            if up_mid is None and info.owner is not None and info.owner.mid > 0:
                up_mid = info.owner.mid

        if cid is None or cid <= 0:
            raise ValueError("无法获取视频 cid，请显式传入 cid")

        params: dict[str, Any] = {"cid": cid}
        if bvid:
            params["bvid"] = bvid
        else:
            params["aid"] = int(aid)
        if up_mid is not None:
            params["up_mid"] = up_mid
        get_wbi(params)
        data = self.session.get(VideoUrls.AI_SUMMARY, params=params)
        if not isinstance(data, dict):
            raise ValueError("视频 AI 总结响应 data 类型错误")
        return VideoAISummary.from_dict(data)

    def get_ai_summary(self, *args, **kwargs) -> VideoAISummary:
        """``fetch_ai_summary`` 的简易别名，返回 dataclass。"""
        return self.fetch_ai_summary(*args, **kwargs)

    def fetch_ai_summary_text(self, *args, **kwargs) -> str:
        """获取视频 AI 总结的纯文本摘要。

        与 ``fetch_ai_summary`` 相比，该方法只返回 ``model_result.summary``；
        视频没有可用 AI 总结时返回空字符串。
        """
        return self.fetch_ai_summary(*args, **kwargs).summary_text

    def get_ai_summary_text(self, *args, **kwargs) -> str:
        """``fetch_ai_summary_text`` 的简易别名，直接返回字符串。"""
        return self.fetch_ai_summary_text(*args, **kwargs)

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

    def get_playurl(self, bvid: str, cid: int, fnval: int = DASH_FNVAL,
                    expected_duration: float = 0) -> DashStreams:
        """获取并严格校验视频播放流。

        DASH 不可用时（老视频没有 DASH 转码）回退到旧式直出流 durl；
        直出流时长明显短于该分P、或时长无法校验时，才判定为试看/预览流。

        :param expected_duration: 该分P的时长（秒），用于识别试看流；0 表示未知
        """
        params = {
            "bvid": bvid, "cid": cid, "qn": 120, "fnver": 0, "fnval": fnval,
            "fourk": 1, "platform": "pc", "high_quality": 1,
        }
        get_wbi(params)
        data = self.session.get(VideoUrls.PLAY, params=params)
        if not isinstance(data, dict):
            raise BiliAPIError(-1, "播放流响应 data 类型错误")
        dash = data.get("dash")
        if not isinstance(dash, dict):
            progressive = self._parse_progressive(data, expected_duration)
            if progressive is not None:
                return DashStreams(progressive=progressive)
            if data.get("durl"):
                raise VideoPreviewOnlyError(
                    f"视频 {bvid} 仅返回试看/预览流（可能是充电专属），无法下载完整视频。"
                )
            raise BiliAPIError(-1, "播放流响应缺少 dash 数据")
        raw_videos = dash.get("video")
        raw_audios = dash.get("audio")
        if not isinstance(raw_videos, list) or not isinstance(raw_audios, list):
            raise BiliAPIError(-1, "播放流响应的 video/audio 字段类型错误")
        videos = []
        for value in raw_videos:
            if not isinstance(value, dict) or not isinstance(value.get("baseUrl"), str) or not value["baseUrl"]:
                continue
            videos.append(VideoStream(url=value["baseUrl"], codecs=value.get("codecs", ""),
                                      width=value.get("width", 0), height=value.get("height", 0),
                                      quality=value.get("id", 0), frame_rate=value.get("frameRate", ""),
                                      size=value.get("size", 0)))
        audios = []
        seen_audio_urls = set()

        def _add_audios(values, kind: str) -> None:
            if isinstance(values, dict):
                values = [values]
            if not isinstance(values, list):
                return
            for value in values:
                if not isinstance(value, dict) or not isinstance(value.get("baseUrl"), str) or not value["baseUrl"]:
                    continue
                if value["baseUrl"] in seen_audio_urls:
                    continue
                seen_audio_urls.add(value["baseUrl"])
                audios.append(AudioStream(url=value["baseUrl"], codecs=value.get("codecs", ""),
                                          bandwidth=value.get("bandwidth", 0), size=value.get("size", 0),
                                          kind=kind))

        _add_audios(raw_audios, "aac")
        # 杜比（30250, E-AC-3）与无损（30251, FLAC）是独立音轨，需要大会员权限才会返回。
        dolby = dash.get("dolby")
        if isinstance(dolby, dict):
            _add_audios(dolby.get("audio"), "dolby")
        flac = dash.get("flac")
        if isinstance(flac, dict):
            _add_audios(flac.get("audio"), "flac")
        if not videos or not audios:
            raise BiliAPIError(-1, "播放流响应不含可用的视频或音频流")
        return DashStreams(video=videos, audio=audios)

    @staticmethod
    def _parse_progressive(data: dict, expected_duration: float) -> Optional[ProgressiveStream]:
        """解析旧式直出流 durl；判定为试看/预览时返回 None。"""
        raw = data.get("durl")
        if not isinstance(raw, list):
            return None
        urls: list[str] = []
        total_size = 0
        total_ms = 0
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("url"), str) or not item["url"]:
                continue
            urls.append(item["url"])
            total_size += int(item.get("size") or 0)
            total_ms += int(item.get("length") or 0)
        if not urls:
            return None
        total_ms = total_ms or int(data.get("timelength") or 0)
        if expected_duration > 0:
            # 预览流只包含开头一小段：时长明显短于该分P即不可下载。
            if total_ms < expected_duration * 1000 * 0.9:
                return None
        elif total_ms <= 0:
            # 既无分P时长可对照、直出流也没给时长：按预览处理，避免下载残缺文件。
            return None
        return ProgressiveStream(
            urls=urls,
            quality=int(data.get("quality") or 0),
            format=data.get("format") or "",
            size=total_size,
            duration_ms=total_ms,
        )

    def _download_progressive(self, stream: ProgressiveStream, save_path: Path, *,
                              progress_cb: Optional[ProgressCallback] = None) -> int:
        """下载直出流；服务端分段时逐段下载后按顺序拼成一个文件。"""
        headers = self.session.session.headers
        cancel_event = getattr(self, "cancel_event", None)
        if len(stream.urls) == 1:
            return download_stream(stream.urls[0], save_path, headers, progress_cb=progress_cb,
                                   cancel_event=cancel_event)
        import shutil
        import tempfile

        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = save_path.with_name(save_path.name + ".part")
        with tempfile.TemporaryDirectory(prefix="bilitools_", dir=save_path.parent) as tmp:
            parts = []
            try:
                for index, url in enumerate(stream.urls):
                    if cancel_event is not None and cancel_event.is_set():
                        raise DownloadCancelled("下载已取消")
                    part = Path(tmp) / f"seg{index:03d}"
                    download_stream(url, part, headers, cancel_event=cancel_event)
                    parts.append(part)
            except DownloadCancelled:
                part_path.unlink(missing_ok=True)
                raise
            try:
                with part_path.open("wb") as output:
                    for part in parts:
                        if cancel_event is not None and cancel_event.is_set():
                            raise DownloadCancelled("下载已取消")
                        with part.open("rb") as source:
                            shutil.copyfileobj(source, output)
                part_path.replace(save_path)
            except BaseException:
                part_path.unlink(missing_ok=True)
                raise
        size = save_path.stat().st_size
        if progress_cb is not None:
            progress_cb(size, size)
        return size

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

    def _effective_quality(self, quality: VideoQuality) -> VideoQuality:
        """应用本账号的清晰度上限（多账号分流时非会员账号最高 1080P）。"""
        cap = getattr(self, "quality_cap", None)
        if cap is not None and int(quality) > int(cap):
            return cap
        return quality

    def _permission_accounts_ref(self) -> list[AccountCapability]:
        return getattr(self, "permission_accounts", [])

    def _permission_cache_ref(self) -> AccountPermissionCache:
        cache = getattr(self, "permission_cache", None)
        if cache is None:
            cache = AccountPermissionCache()
            self.permission_cache = cache
        return cache

    def _permission_service(self, cap: AccountCapability) -> "VideoService":
        """为权限换号临时创建一个独立会话的服务（用完即关）。"""
        service = VideoService(
            session=BiliSession(cookie_path=cap.cookie_path),
            default_dir=self.default_dir,
            cancel_event=getattr(self, "cancel_event", None),
            permission_accounts=self._permission_accounts_ref(),
            permission_cache=self._permission_cache_ref(),
            cap_non_vip_quality=getattr(self, "cap_non_vip_quality", None),
        )
        service._owns_session = True
        return service

    def _release_service(self, service: Optional["VideoService"]) -> None:
        """关闭权限换号时临时创建的会话；本服务自身不关闭。"""
        if service is None or service is self:
            return
        try:
            service.session.close()
        except Exception:
            logger.warning("关闭权限换号会话失败", exc_info=True)

    def _streams_via(self, service: "VideoService", bvid: str, page: int):
        """用指定账号取视频信息+播放流；无权限时抛对应异常。"""
        info = service.fetch_info(bvid)
        if info.is_upower_exclusive and not info.is_upower_play:
            raise VideoChargingError(
                f"视频 {bvid} 为充电专属，当前账号未充电/未购买，无法下载完整内容。"
            )
        target = service._resolve_page(info, page)
        if target.cid is None or target.cid == 0:
            raise ValueError(f"视频 {bvid} 第 {page} 分P 的 cid 获取失败，无法下载。")
        dash = service.get_playurl(bvid, target.cid, expected_duration=target.duration)
        return info, target, dash

    def _ordered_permission_accounts(self, up_mid: int) -> list[AccountCapability]:
        """权限换号候选：同一 UP 已知可播放的账号排最前。"""
        candidates = [
            cap for cap in self._permission_accounts_ref()
            if not capability_matches_session(cap, self.session)
        ]
        cached = self._permission_cache_ref().upower_account(up_mid)
        if cached:
            candidates.sort(key=lambda cap: 0 if same_account(cap.cookie_path, cached) else 1)
        return candidates

    def _retry_with_accounts(self, bvid: str, page: int, up_mid: int,
                             first_error: Exception) -> tuple[VideoInfo, DashStreams, "VideoService"]:
        """当前账号无权限（充电/试看）时，依次用其它账号完整重取。"""
        for cap in self._ordered_permission_accounts(up_mid):
            service = self._permission_service(cap)
            try:
                info, _target, dash = self._streams_via(service, bvid, page)
            except (VideoChargingError, VideoPreviewOnlyError, BiliAuthError) as exc:
                service.session.close()
                logger.info("视频 %s 账号「%s」无播放权限，尝试其它账号。", bvid, cap.uname or cap.mid)
                if isinstance(exc, VideoChargingError):
                    first_error = exc
                continue
            except Exception:
                service.session.close()
                raise
            self._permission_cache_ref().remember_upower_account(up_mid, cap.cookie_path)
            logger.info("视频 %s 当前账号无播放权限，改用账号「%s」。", bvid, cap.uname or cap.mid)
            return info, dash, service
        raise first_error

    def _probe_member_account(self, bvid: str, target: VideoPage, quality: Optional[VideoQuality],
                              dash: DashStreams):
        """当前账号非会员且请求会员档时，用会员账号复核能否取得更高清晰度。"""
        if quality is None or int(quality) <= int(VideoQuality.P1080):
            return None
        current_best = _best_quality(dash)
        if current_best >= int(quality):
            return None
        cached = self._permission_cache_ref().max_quality(bvid, target.cid)
        if cached is not None and cached <= current_best:
            return None
        own = capability_for(self.session, self._permission_accounts_ref())
        if own is None or own.is_vip is not False:
            # 会员状态未知时按会员处理，避免每个视频都多一次探测请求。
            return None
        candidates = [
            cap for cap in self._permission_accounts_ref()
            if cap.is_vip and not capability_matches_session(cap, self.session)
        ]
        if not candidates:
            logger.debug("视频 %s 请求 %s，当前账号无大会员且没有其它会员账号，按可用清晰度下载。",
                         bvid, quality.display_name)
            return None
        for cap in candidates:
            service = self._permission_service(cap)
            try:
                info, candidate_target, candidate_dash = self._streams_via(service, bvid, target.page)
            except (VideoChargingError, VideoPreviewOnlyError, BiliAuthError):
                service.session.close()
                continue
            except Exception:
                service.session.close()
                raise
            candidate_best = _best_quality(candidate_dash)
            self._permission_cache_ref().remember_max_quality(bvid, candidate_target.cid, candidate_best)
            if candidate_best > current_best:
                logger.info("视频 %s 当前账号无大会员，改用会员账号「%s」获取更高清晰度。",
                            bvid, cap.uname or cap.mid)
                return info, candidate_dash, service
            service.session.close()
            return None
        return None

    def _fetch_streams(self, bvid: str, page: int = 1,
                       quality: Optional[VideoQuality] = None) -> tuple[VideoInfo, DashStreams, "VideoService"]:
        """获取视频信息 + 指定分P的播放流（DASH，或老视频的直出流）。

        账号权限不足时按候选账号重试（充电/试看），请求会员档时用会员账号
        复核清晰度；返回值中的 service 是**实际取流账号**，下载必须用它。

        :param quality: 请求的清晰度，用于判断是否需要会员账号复核；None 表示不关心
        :return: (VideoInfo, DashStreams, 实际取流账号的 VideoService)
        """
        # 每种下载（视频、音频、合成）都先复用同一条信息链：
        # BV -> VIEW -> VideoInfo -> 目标分P/cid -> PLAY -> DASH/直出流。
        info = self.fetch_info(bvid)
        up_mid = info.owner.mid if info.owner is not None else 0
        if info.is_upower_exclusive and not info.is_upower_play:
            error = VideoChargingError(
                f"视频 {bvid} 为充电专属，当前账号未充电/未购买，无法下载完整内容。"
            )
            return self._retry_with_accounts(bvid, page, up_mid, error)
        target = self._resolve_page(info, page)
        if target.cid is None or target.cid == 0:
            raise ValueError(f"视频 {bvid} 第 {page} 分P 的 cid 获取失败，无法下载。")
        try:
            dash = self.get_playurl(bvid, target.cid, expected_duration=target.duration)
        except VideoPreviewOnlyError as error:
            return self._retry_with_accounts(bvid, page, up_mid, error)
        if info.is_upower_exclusive:
            self._permission_cache_ref().remember_upower_account(up_mid, getattr(self.session, "cookie_path", ""))
        probed = self._probe_member_account(bvid, target, quality, dash)
        if probed is not None:
            return probed
        return info, dash, self

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
        """稿件不可下载（不存在/不可见/审核中/仅UP主可见）：批量下载时跳过该视频。"""
        return isinstance(exc, BiliAPIError) and exc.code in VIDEO_UNAVAILABLE_REASONS

    def _is_risk_control_error(self, exc: Exception) -> bool:
        """是否触发风控（-412 触发风控 / -403 被拒绝访问），这类错误稍作等待后重试通常可恢复。"""
        return isinstance(exc, (BiliRiskError, BiliForbiddenError))

    def _raise_if_cancelled(self) -> None:
        """用户终止后，批量循环在进入下一个文件前立即停止。"""
        event = getattr(self, "cancel_event", None)
        if event is not None and event.is_set():
            raise DownloadCancelled("下载已取消")

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
        - 单个文件下载失败（CDN 超时等）：返回 ``_RETRY_OUTCOME``，由批量入口排到
          队列最后统一重试；
        - 其余异常：原样抛出。

        :param bvid: 视频BV号（仅用于日志）
        :param action: 无参可调用对象，完成该视频（稿件）的下载
        :param label: 批量任务描述（收藏夹/合集/UP主名称），仅用于日志
        :param retries: 触发风控后的最大重试次数
        :param risk_gate: 并发下载时的风控协调器；None 表示顺序下载（本地退避）
        :return: action 的返回值；不可见/无权限时为 None；可重试的下载失败为 _RETRY_OUTCOME
        """
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            self._raise_if_cancelled()
            if risk_gate is not None:
                # 风控后所有线程在下一次获取信息前暂停（每个线程暂停时长单独计算）
                risk_gate.pause_before_fetch()
            try:
                return action()
            except DownloadCancelled:
                raise
            except Exception as e:
                if isinstance(e, (VideoChargingError, VideoPreviewOnlyError)):
                    logger.warning("视频 %s 无法下载完整内容，跳过（%s）：%s", bvid, label, e)
                    return None
                if self._is_video_unavailable_error(e):
                    reason = VIDEO_UNAVAILABLE_REASONS.get(e.code, "不可下载")
                    logger.warning("视频 %s 跳过：%s（%s）。", bvid, reason, label)
                    return None
                if isinstance(e, FFmpegNotFoundError):
                    raise
                if isinstance(e, DownloadError):
                    cancel_event = getattr(self, "cancel_event", None)
                    if cancel_event is not None and cancel_event.is_set():
                        raise DownloadCancelled("下载已取消") from e
                    # 批量任务里单个文件下载失败（CDN 超时等）不中断任务，
                    # 交给调用方排到队尾最后重试。
                    logger.error("视频 %s 下载失败，稍后重试（%s）：%s", bvid, label, e)
                    return _RETRY_OUTCOME
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
        page = int(page) if page is not None else None
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
                stem = path.stem.casefold()
                if bvid.casefold() not in stem:
                    continue
                if path.suffix.casefold().lstrip(".") not in extensions:
                    continue
                if page is not None and not _has_page_tag(stem, page):
                    # 第 1 分P可命中“无分P标签”的单P文件；
                    # 其它分P必须精确匹配 -Pxx-，避免把别的分P当成已下载。
                    if page != 1 or _PAGE_TAG_RE.search(stem):
                        continue
                return path
        return None

    def download_video(
            self, bvid: str, dir: Optional[Path] = None, *, page: int = 1,
            quality: VideoQuality = VideoQuality.HD4K, progress_cb: Optional[ProgressCallback] = None,
            progress: Optional[BatchProgress] = None, filename: Optional[str] = None,
            cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None, force: bool = False,
    ) -> DownloadResult:
        self._raise_if_cancelled()
        quality = self._effective_quality(quality)
        save_dir = Path(dir) if dir is not None else self.default_dir
        existing = None if force else self._find_downloaded_file(
            bvid, {"mp4", "flv", "m4s"}, page=page, roots=self._cache_roots(save_dir, cache_dirs))
        if existing is not None:
            return DownloadResult(path=existing, media_type="video", size=existing.stat().st_size, cached=True)
        info, dash, stream_service = self._fetch_streams(bvid, page, quality=quality)
        auto = False
        success = False
        try:
            stream = dash.progressive if dash.progressive is not None else dash.pick_video(quality)
            if stream is None:
                raise ValueError(f"视频 {bvid} 第 {page} 分P 没有可用的视频流。")
            safe_name = filename or self._default_filename(info, bvid, page, stream.ext)
            save_path = resolve_save_path(save_dir, safe_name)
            if save_path.is_file() and save_path.stat().st_size > 0 and not force:
                return DownloadResult(path=save_path, media_type="video",
                                      size=save_path.stat().st_size, cached=True)
            progress, auto = self._auto_progress(safe_name, progress, progress_cb)
            if progress:
                picked = VideoQuality.from_qn(stream.quality)
                if picked is not None:
                    progress.set_quality(picked)
            if dash.progressive is not None:
                size = stream_service._download_progressive(
                    dash.progressive, save_path,
                    progress_cb=progress.make_stream_callback() if progress else progress_cb)
            else:
                size = download_stream(stream.url, save_path, stream_service.session.session.headers,
                                       progress_cb=progress.make_stream_callback() if progress else progress_cb,
                                       overwrite=force, cancel_event=getattr(self, "cancel_event", None))
            success = True
            return DownloadResult(path=save_path, media_type="video", size=size)
        finally:
            self._release_service(stream_service)
            if auto:
                progress.finish(success=success)

    def download_audio(
            self, bvid: str, dir: Optional[Path] = None, *, page: int = 1,
            progress_cb: Optional[ProgressCallback] = None, progress: Optional[BatchProgress] = None,
            filename: Optional[str] = None, cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None,
            force: bool = False,
    ) -> DownloadResult:
        self._raise_if_cancelled()
        save_dir = Path(dir) if dir is not None else self.default_dir
        existing = None if force else self._find_downloaded_file(
            bvid, {"m4a", "mp3", "flac", "aac", "mka"}, page=page,
            roots=self._cache_roots(save_dir, cache_dirs))
        if existing is not None:
            return DownloadResult(path=existing, media_type="audio", size=existing.stat().st_size, cached=True)
        info, dash, stream_service = self._fetch_streams(bvid, page)
        auto = False
        success = False
        try:
            import tempfile
            progressive = dash.progressive
            candidates = dash.audio_candidates()
            if progressive is None and not candidates:
                raise ValueError(f"视频 {bvid} 第 {page} 分P 没有可用的音频流。")
            if progressive is not None:
                # 直出流音视频合一：先下载完整文件，再用 ffmpeg 提取音轨。
                safe_name = filename or self._default_filename(info, bvid, page, "m4a")
                save_path = resolve_save_path(save_dir, safe_name)
                if save_path.is_file() and save_path.stat().st_size > 0 and not force:
                    return DownloadResult(path=save_path, media_type="audio",
                                          size=save_path.stat().st_size, cached=True)
                progress, auto = self._auto_progress(safe_name, progress, progress_cb)
                if not ffmpeg_available():
                    raise FFmpegNotFoundError(
                        "该视频仅提供直出流（音视频合一），提取音频需要 ffmpeg，且未安装 imageio-ffmpeg 库。")
                with tempfile.TemporaryDirectory(prefix="bilitools_", dir=save_dir) as tmp:
                    source = Path(tmp) / f"source.{progressive.ext}"
                    stream_service._download_progressive(
                        progressive, source,
                        progress_cb=progress.make_stream_callback() if progress else progress_cb)
                    if progress:
                        progress.status("直出流下载完成，正在提取音频...")
                    extract_audio(source, save_path, cancel_event=getattr(self, "cancel_event", None))
                success = True
                return DownloadResult(path=save_path, media_type="audio", size=save_path.stat().st_size)

            # 优先杜比/无损，失败逐个回退到下一音轨（最后是 AAC）。
            last_error: Optional[Exception] = None
            for index, stream in enumerate(candidates):
                ext = _audio_output_ext(stream)
                safe_name = filename or self._default_filename(info, bvid, page, ext)
                save_path = resolve_save_path(save_dir, safe_name)
                if save_path.is_file() and save_path.stat().st_size > 0 and not force:
                    return DownloadResult(path=save_path, media_type="audio",
                                          size=save_path.stat().st_size, cached=True)
                attempt_progress, attempt_auto = self._auto_progress(safe_name, progress, progress_cb)
                attempt_success = False
                try:
                    if stream.kind in ("dolby", "flac"):
                        if not ffmpeg_available():
                            raise FFmpegNotFoundError("杜比/无损音轨需要 ffmpeg 封装")
                        with tempfile.TemporaryDirectory(prefix="bilitools_", dir=save_dir) as tmp:
                            source = Path(tmp) / f"source.{stream.ext}"
                            download_stream(
                                stream.url, source, stream_service.session.session.headers,
                                progress_cb=(attempt_progress.make_stream_callback()
                                             if attempt_progress else progress_cb),
                                cancel_event=getattr(self, "cancel_event", None))
                            self._raise_if_cancelled()
                            if attempt_progress:
                                attempt_progress.status(
                                    f"{_audio_label(stream)}下载完成，正在封装音轨...")
                            extract_audio(source, save_path,
                                          cancel_event=getattr(self, "cancel_event", None))
                        size = save_path.stat().st_size
                    else:
                        size = download_stream(
                            stream.url, save_path, stream_service.session.session.headers,
                            progress_cb=(attempt_progress.make_stream_callback()
                                         if attempt_progress else progress_cb),
                            overwrite=force, cancel_event=getattr(self, "cancel_event", None))
                    attempt_success = True
                    return DownloadResult(path=save_path, media_type="audio", size=size)
                except DownloadCancelled:
                    raise
                except FFmpegNotFoundError as exc:
                    last_error = exc
                    if index == len(candidates) - 1:
                        raise
                    logger.warning("音轨 %s 需要 ffmpeg，回退下一音轨：%s", _audio_label(stream), exc)
                    continue
                except DownloadError as exc:
                    last_error = exc
                    if index == len(candidates) - 1:
                        raise
                    logger.warning("音轨 %s 下载失败，回退下一音轨：%s", _audio_label(stream), exc)
                    continue
                finally:
                    if attempt_auto:
                        attempt_progress.finish(success=attempt_success)
            if last_error is not None:
                raise last_error
            raise ValueError(f"视频 {bvid} 第 {page} 分P 没有可用的音频流。")
        finally:
            self._release_service(stream_service)
            if auto:
                progress.finish(success=success)

    def download_video_with_audio(
            self, bvid: str, dir: Optional[Path] = None, *, page: int = 1,
            quality: VideoQuality = VideoQuality.HD4K, keep_parts: bool = False,
            progress_cb: Optional[ProgressCallback] = None, progress: Optional[BatchProgress] = None,
            filename: Optional[str] = None, cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None,
            force: bool = False,
    ) -> DownloadResult:
        import tempfile
        self._raise_if_cancelled()
        quality = self._effective_quality(quality)
        save_dir = Path(dir) if dir is not None else self.default_dir
        existing = None if force else self._find_downloaded_file(
            bvid, {"mp4", "flv", "m4s"}, page=page, roots=self._cache_roots(save_dir, cache_dirs))
        if existing is not None:
            return DownloadResult(path=existing, media_type="video", size=existing.stat().st_size, cached=True)
        info, dash, stream_service = self._fetch_streams(bvid, page, quality=quality)
        auto = False
        success = False
        try:
            if dash.progressive is not None:
                # 直出流已含音频，直接保存，无需 ffmpeg 合成。
                stream = dash.progressive
                safe_name = filename or self._default_filename(info, bvid, page, stream.ext)
                save_path = resolve_save_path(save_dir, safe_name)
                if save_path.is_file() and save_path.stat().st_size > 0 and not force:
                    return DownloadResult(path=save_path, media_type="video",
                                          size=save_path.stat().st_size, cached=True)
                progress, auto = self._auto_progress(safe_name, progress, progress_cb)
                if progress:
                    picked = VideoQuality.from_qn(stream.quality)
                    if picked is not None:
                        progress.set_quality(picked)
                size = stream_service._download_progressive(
                    stream, save_path,
                    progress_cb=progress.make_stream_callback() if progress else progress_cb)
                success = True
                return DownloadResult(path=save_path, media_type="video", size=size)
            if not ffmpeg_available():
                raise FFmpegNotFoundError("未检测到 ffmpeg，且未安装 imageio-ffmpeg 库，无法进行音视频合成。")
            video_stream = dash.pick_video(quality)
            audio_candidates = dash.audio_candidates()
            if video_stream is None or not audio_candidates:
                raise ValueError(f"视频 {bvid} 第 {page} 分P 的视频流或音频流不可用，无法合成。")
            safe_name = filename or self._default_filename(info, bvid, page, "mp4")
            save_path = resolve_save_path(save_dir, safe_name)
            if save_path.is_file() and save_path.stat().st_size > 0 and not force:
                return DownloadResult(path=save_path, media_type="video",
                                      size=save_path.stat().st_size, cached=True)
            progress, auto = self._auto_progress(safe_name, progress, progress_cb)
            if progress:
                picked = VideoQuality.from_qn(video_stream.quality)
                if picked is not None:
                    progress.set_quality(picked)
            with tempfile.TemporaryDirectory(prefix="bilitools_", dir=save_dir) as tmp:
                tmp_dir = Path(tmp)
                video_tmp = tmp_dir / f"video.{video_stream.ext}"
                state = {"id": 0, "last": 0}

                def cb(done: int, total: Optional[int]) -> None:
                    if progress:
                        delta = max(0, done - state["last"])
                        progress.add(delta, total, stream_id=state["id"])
                        state["last"] = done
                    elif progress_cb:
                        progress_cb(done, total)

                download_stream(video_stream.url, video_tmp, stream_service.session.session.headers,
                                progress_cb=cb, cancel_event=getattr(self, "cancel_event", None))
                if progress:
                    progress.status("视频流下载完成，正在下载音频流...")

                # 音轨优先杜比/无损；下载或合成失败时逐个回退，最后是 AAC。
                chosen_audio = None
                chosen_audio_tmp = None
                last_error: Optional[Exception] = None
                for index, audio_stream in enumerate(audio_candidates):
                    audio_tmp = tmp_dir / f"audio_{index}.{audio_stream.ext}"
                    state["id"], state["last"] = 1, 0
                    try:
                        download_stream(audio_stream.url, audio_tmp,
                                        stream_service.session.session.headers,
                                        progress_cb=cb,
                                        cancel_event=getattr(self, "cancel_event", None))
                        if progress:
                            progress.status("正在用 ffmpeg 合成音视频...")
                        merge_video_audio(video_tmp, audio_tmp, save_path, progress_cb=progress_cb,
                                          cancel_event=getattr(self, "cancel_event", None))
                        chosen_audio, chosen_audio_tmp = audio_stream, audio_tmp
                        break
                    except DownloadCancelled:
                        raise
                    except FFmpegNotFoundError:
                        raise
                    except DownloadError as exc:
                        last_error = exc
                        audio_tmp.unlink(missing_ok=True)
                        audio_tmp.with_name(audio_tmp.name + ".part").unlink(missing_ok=True)
                        if index == len(audio_candidates) - 1:
                            raise
                        logger.warning("音轨 %s 下载/合成失败，回退下一音轨：%s",
                                       _audio_label(audio_stream), exc)
                        continue
                if chosen_audio is None:
                    raise last_error or DownloadError("音轨下载失败")
                if keep_parts:
                    video_tmp.replace(save_dir / f"{save_path.stem}.video.{video_stream.ext}")
                    chosen_audio_tmp.replace(
                        save_dir / f"{save_path.stem}.audio.{chosen_audio.ext}")
            success = True
            return DownloadResult(path=save_path, media_type="video", size=save_path.stat().st_size)
        finally:
            self._release_service(stream_service)
            if auto:
                progress.finish(success=success)

    @staticmethod
    def _decode_danmaku_xml(content: bytes) -> bytes:
        """Decode the XML danmaku response, including deflate variants."""
        if not isinstance(content, (bytes, bytearray)) or not content:
            raise ValueError("弹幕响应为空")
        data = bytes(content)
        candidates = [data]
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                decoded = zlib.decompress(data, wbits)
            except zlib.error:
                continue
            if decoded not in candidates:
                candidates.append(decoded)
        for candidate in candidates:
            stripped = candidate.lstrip(b"\xef\xbb\xbf \t\r\n")
            if stripped.startswith(b"<") and b"<i" in stripped[:512]:
                return candidate
        raise ValueError("弹幕响应不是有效的 XML")

    @staticmethod
    def _ass_time(seconds: float) -> str:
        """Format seconds as an ASS timestamp."""
        centiseconds = max(0, int(round(seconds * 100)))
        hours, remainder = divmod(centiseconds, 360000)
        minutes, remainder = divmod(remainder, 6000)
        secs, cents = divmod(remainder, 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{cents:02d}"

    @staticmethod
    def _ass_text(text: str) -> str:
        """Escape user text so it cannot accidentally become an ASS tag."""
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        return text.replace("\n", "\\N")

    @staticmethod
    def _danmaku_xml_to_ass(content: bytes, *, play_res_x: int = 1920,
                            play_res_y: int = 1080, scroll_duration: float = 8.0) -> bytes:
        """Convert Bilibili XML danmaku to a PotPlayer-compatible ASS file."""
        try:
            root = ET.fromstring(content.decode("utf-8-sig", errors="replace"))
        except (ET.ParseError, UnicodeError) as exc:
            raise ValueError("弹幕 XML 解析失败") from exc
        if root.tag.rsplit("}", 1)[-1] != "i":
            raise ValueError("弹幕 XML 根节点不是 i")
        if play_res_x <= 0 or play_res_y <= 0 or scroll_duration <= 0:
            raise ValueError("ASS 视频尺寸和弹幕持续时间必须为正数")

        header = [
            "[Script Info]",
            "; Converted from Bilibili XML danmaku",
            "ScriptType: v4.00+",
            f"PlayResX: {play_res_x}",
            f"PlayResY: {play_res_y}",
            "ScaledBorderAndShadow: yes",
            "WrapStyle: 2",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Danmaku,Microsoft YaHei,36,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,7,20,20,20,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
        events: list[str] = []
        lane_height = 52
        lane_count = max(1, (play_res_y - 100) // lane_height)
        scroll_lanes: list[list[tuple[float, float]]] = [[] for _ in range(lane_count)]
        top_lanes: list[float] = []
        bottom_lanes: list[float] = []
        top_count = max(1, min(4, lane_count // 3 or 1))
        bottom_count = top_count

        def choose_lane(lanes: list[list[tuple[float, float]]], start: float, end: float) -> int:
            for index, occupied in enumerate(lanes):
                while occupied and occupied[0][1] <= start:
                    occupied.pop(0)
                if not occupied or occupied[-1][1] <= start:
                    occupied.append((start, end))
                    return index
            index = min(range(len(lanes)), key=lambda item: lanes[item][0][1])
            lanes[index] = [(start, end)]
            return index

        def ass_color(value: str) -> str:
            try:
                rgb = int(value or "16777215", 0) if value.lower().startswith("0x") else int(value or "16777215")
            except (TypeError, ValueError):
                rgb = 16777215
            rgb = max(0, min(0xFFFFFF, rgb))
            red, green, blue = (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF
            return f"&H{blue:02X}{green:02X}{red:02X}&"

        for node in root:
            if node.tag.rsplit("}", 1)[-1] != "d":
                continue
            parts = (node.attrib.get("p") or "").split(",")
            if len(parts) < 4:
                continue
            try:
                start = max(0.0, float(parts[0]))
                mode = int(float(parts[1]))
                font_size = max(12, min(72, int(float(parts[2] or 36))))
            except (TypeError, ValueError):
                continue
            text = VideoService._ass_text("".join(node.itertext()))
            if not text:
                continue
            end = start + scroll_duration
            color = ass_color(parts[3])
            tags = f"{{\\fs{font_size}\\c{color}}}"
            if mode in (4, 5):
                if mode == 5:
                    lane = len(top_lanes) % top_count
                    y = 40 + lane * lane_height
                    top_lanes.append(end)
                    alignment = 8
                else:
                    lane = len(bottom_lanes) % bottom_count
                    y = play_res_y - 40 - lane * lane_height
                    bottom_lanes.append(end)
                    alignment = 2
                text_line = f"{{\\an{alignment}\\pos({play_res_x // 2},{y})}}{tags}{text}"
            else:
                lane = choose_lane(scroll_lanes, start, end)
                y = 45 + lane * lane_height
                estimate = max(60, len(text.replace("\\N", "")) * font_size)
                if mode == 6:
                    effect = f"{{\\move({-estimate},{y},{play_res_x + estimate},{y},0,{int(scroll_duration * 1000)})}}"
                else:
                    effect = f"{{\\move({play_res_x + estimate},{y},{-estimate},{y},0,{int(scroll_duration * 1000)})}}"
                text_line = f"{effect}{tags}{text}"
            events.append(
                f"Dialogue: 0,{VideoService._ass_time(start)},{VideoService._ass_time(end)},Danmaku,,0,0,0,,{text_line}"
            )

        header.extend(events)
        return ("\n".join(header) + "\n").encode("utf-8-sig")

    def download_danmaku(
            self, bvid: str, dir: Optional[Path] = None, *, page: int = 1,
            progress_cb: Optional[ProgressCallback] = None, progress: Optional[BatchProgress] = None,
            filename: Optional[str] = None,
            cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None, force: bool = False,
            format: str = "ass",
    ) -> DownloadResult:
        """Download danmaku as ASS for PotPlayer, or XML for compatibility.

        ``format`` accepts ``"ass"`` (default) and ``"xml"``. The generated
        filename follows the video filename and only changes its extension.
        """
        output_format = str(format or "ass").lower().lstrip(".")
        if output_format not in {"ass", "xml"}:
            raise ValueError("弹幕格式只支持 ass 或 xml")
        extension = output_format
        self._raise_if_cancelled()
        save_dir = Path(dir) if dir is not None else self.default_dir
        existing = None if force else self._find_downloaded_file(
            bvid, {extension}, page=page, roots=self._cache_roots(save_dir, cache_dirs)
        )
        if existing is not None:
            return DownloadResult(
                path=existing, media_type="danmaku", size=existing.stat().st_size, cached=True
            )

        info = self.fetch_info(bvid)
        target = self._resolve_page(info, page)
        if not target.cid:
            raise ValueError(f"视频 {bvid} 第 {page} 分P 的 cid 获取失败，无法获取弹幕。")
        safe_name = filename or self._default_filename(info, bvid, page, extension)
        save_path = resolve_save_path(save_dir, safe_name)
        if save_path.is_file() and save_path.stat().st_size > 0 and not force:
            return DownloadResult(
                path=save_path, media_type="danmaku", size=save_path.stat().st_size, cached=True
            )

        progress, auto = self._auto_progress(safe_name, progress, progress_cb)
        success = False
        try:
            content = self.session.get_raw(
                VideoUrls.DANMAKU,
                params={"oid": target.cid},
                max_bytes=64 * 1024 * 1024,
            )
            self._raise_if_cancelled()
            content = self._decode_danmaku_xml(content)
            if output_format == "ass":
                content = self._danmaku_xml_to_ass(content)
            part = save_path.with_name(save_path.name + ".part")
            part.write_bytes(content)
            part.replace(save_path)
            if progress:
                progress.update(len(content), len(content))
            elif progress_cb:
                progress_cb(len(content), len(content))
            success = True
            return DownloadResult(path=save_path, media_type="danmaku", size=len(content))
        finally:
            if auto:
                progress.finish(success=success)

    def download_cover(
            self, bvid: str, dir: Optional[Path] = None, *, progress_cb: Optional[ProgressCallback] = None,
            progress: Optional[BatchProgress] = None, filename: Optional[str] = None,
            cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None, force: bool = False,
    ) -> DownloadResult:
        self._raise_if_cancelled()
        save_dir = Path(dir) if dir is not None else self.default_dir
        existing = None if force else self._find_downloaded_file(
            bvid, {"jpg", "jpeg", "png", "webp"}, roots=self._cache_roots(save_dir, cache_dirs))
        if existing is not None:
            return DownloadResult(path=existing, media_type="cover", size=existing.stat().st_size, cached=True)
        self._raise_if_cancelled()
        info = self.fetch_info(bvid)
        if not info.pic:
            raise ValueError(f"视频 {bvid} 的封面地址获取失败。")
        ext = "png" if info.pic.lower().split("?", 1)[0].endswith(".png") else "jpg"
        safe_name = filename or build_download_filename(info.title, bvid, ext)
        save_path = resolve_save_path(save_dir, safe_name)
        if save_path.is_file() and save_path.stat().st_size > 0 and not force:
            return DownloadResult(path=save_path, media_type="cover", size=save_path.stat().st_size, cached=True)
        progress, auto = self._auto_progress(safe_name, progress, progress_cb)
        success = False
        try:
            content = self.session.get_raw(info.pic, max_bytes=16 * 1024 * 1024)
            self._raise_if_cancelled()
            if not _valid_image_bytes(content):
                raise ValueError("封面响应不是受支持的图片格式")
            part = save_path.with_name(save_path.name + ".part")
            part.write_bytes(content)
            part.replace(save_path)
            if progress:
                progress.update(len(content), len(content))
            elif progress_cb:
                progress_cb(len(content), len(content))
            success = True
            return DownloadResult(path=save_path, media_type="cover", size=len(content))
        finally:
            if auto:
                progress.finish(success=success)

    def download_all_pages(
            self, bvid: str, dir: Optional[Path] = None, *,
            quality: VideoQuality = VideoQuality.HD4K, media_type: str = "video_with_audio",
            progress_cb: Optional[ProgressCallback] = None, progress: Optional[BatchProgress] = None,
            cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None, force: bool = False,
            threads: int = 1, account_sessions: Optional[list] = None,
    ) -> list:
        """下载某视频的全部分P；仍失败的分P会抛 DownloadError（单视频任务据此提示失败）。"""
        results, failed = self._download_all_pages_report(
            bvid, dir, quality=quality, media_type=media_type,
            progress_cb=progress_cb, progress=progress,
            cache_dirs=cache_dirs, force=force,
            threads=threads, account_sessions=account_sessions,
        )
        if failed:
            raise DownloadError(f"视频 {bvid} 有 {len(failed)} 个分P下载失败：{failed}")
        return results

    def _download_all_pages_report(
            self, bvid: str, dir: Optional[Path] = None, *,
            quality: VideoQuality = VideoQuality.HD4K, media_type: str = "video_with_audio",
            progress_cb: Optional[ProgressCallback] = None, progress: Optional[BatchProgress] = None,
            cache_dirs: Optional[Union[Iterable[Path], Path, str]] = None, force: bool = False,
            threads: int = 1, account_sessions: Optional[list] = None,
            only_pages: Optional[Iterable[int]] = None,
    ) -> tuple[list, list]:
        """下载分P并返回 ``(成功结果, 仍失败的分P序号)``；失败项由批量入口排到队尾重试。"""
        if media_type not in _ALLOWED_MEDIA_TYPES:
            raise ValueError(f"不支持的媒体类型：{media_type!r}，允许值：{sorted(_ALLOWED_MEDIA_TYPES)}")
        info = self.fetch_info(bvid)
        if not info.pages:
            raise ValueError(f"视频 {bvid} 没有分P信息，无法批量下载。")
        # 封面属于稿件级资源，没有 page-specific URL；多P只下载一次，避免重复覆盖同一个文件。
        pages = info.pages if media_type != "cover" else info.pages[:1]
        if only_pages is not None:
            wanted = {int(value) for value in only_pages}
            pages = [page_obj for page_obj in pages if page_obj.page in wanted]
            if not pages:
                return [], []
        threads = max(1, int(threads))
        if progress is None:
            progress_cls = ParallelBatchProgress if threads > 1 and len(pages) > 1 else BatchProgress
            progress = progress_cls(n=len(pages), label=f"视频 {bvid}")

        def run_page(service, page_obj, index):
            service._raise_if_cancelled()
            display_ext = {"video": "mp4", "audio": "m4a", "cover": "jpg", "danmaku": "ass"}.get(media_type, "mp4")
            display_name = self._default_filename(info, bvid, page_obj.page, display_ext)
            progress.start(index, display_name)
            try:
                logger.debug("正在下载 %s 第 %d/%d 分P：%s", bvid, page_obj.page, len(pages), page_obj.part)
                if media_type == "video":
                    result = service.download_video(bvid, dir, page=page_obj.page, quality=quality,
                                                    progress_cb=progress_cb, progress=progress,
                                                    cache_dirs=cache_dirs, force=force)
                elif media_type == "audio":
                    result = service.download_audio(bvid, dir, page=page_obj.page,
                                                    progress_cb=progress_cb, progress=progress,
                                                    cache_dirs=cache_dirs, force=force)
                elif media_type == "cover":
                    result = service.download_cover(bvid, dir, progress_cb=progress_cb, progress=progress,
                                                    cache_dirs=cache_dirs, force=force)
                elif media_type == "danmaku":
                    result = service.download_danmaku(bvid, dir, page=page_obj.page,
                                                      progress_cb=progress_cb, progress=progress,
                                                      cache_dirs=cache_dirs, force=force)
                else:
                    result = service.download_video_with_audio(bvid, dir, page=page_obj.page, quality=quality,
                                                               progress_cb=progress_cb, progress=progress,
                                                               cache_dirs=cache_dirs, force=force)
            except Exception:
                progress.finish(success=False)
                raise
            progress.finish()
            return result

        def safe_run(service, page_obj, index):
            """分P失败不立即中断：先继续其余分P，最后统一重试失败的。"""
            try:
                return run_page(service, page_obj, index), None
            except DownloadCancelled:
                raise
            except DownloadError as exc:
                service._raise_if_cancelled()
                logger.error("视频 %s 第 %d 分P 下载失败，稍后重试：%s",
                             bvid, page_obj.page, exc)
                return None, (page_obj, index)

        if threads > 1 and len(pages) > 1:
            services = self._account_services(account_sessions, threads)
            try:
                def work(page_obj, idx):
                    service = services[idx % len(services)]
                    return safe_run(service, page_obj, idx + 1)

                pairs = parallel_run(pages, work, threads)
            finally:
                self._close_owned_services(services)
        else:
            pairs = [safe_run(self, page_obj, i) for i, page_obj in enumerate(pages, 1)]

        results = [result for result, failed in pairs if result is not None]
        retry_pages = [failed for _result, failed in pairs if failed is not None]
        failed_pages = []
        if retry_pages:
            self._raise_if_cancelled()
            logger.info("视频 %s 有 %d 个分P失败，最后重试。", bvid, len(retry_pages))
            for page_obj, index in retry_pages:
                self._raise_if_cancelled()
                try:
                    results.append(run_page(self, page_obj, index))
                except DownloadCancelled:
                    raise
                except DownloadError as exc:
                    logger.error("视频 %s 第 %d 分P重试仍失败：%s",
                                 bvid, page_obj.page, exc)
                    failed_pages.append(page_obj.page)
        return results, failed_pages

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
                self._raise_if_cancelled()
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
    ) -> tuple[list, int, list]:
        """下载一个稿件；失败分P不中断，返回 ``(结果, 新序号, 失败分P序号)``。"""
        if media_type not in _ALLOWED_MEDIA_TYPES:
            raise ValueError(f"不支持的媒体类型：{media_type!r}")
        info = self.fetch_info(episode.bvid)
        new_results = []
        failed_pages = []
        page_objs = episode.pages if episode.is_multi_page and media_type != "cover" else [
            VideoPage(page=1, cid=info.cid or 0, part=info.title)]
        for page_obj in page_objs:
            self._raise_if_cancelled()
            file_idx += 1
            display_ext = {"video": "mp4", "audio": "m4a", "cover": "jpg", "danmaku": "ass"}.get(media_type, "mp4")
            display_name = self._default_filename(info, episode.bvid, page_obj.page, display_ext)
            progress.start(file_idx, display_name)
            success = False
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
                elif media_type == "danmaku":
                    result = self.download_danmaku(episode.bvid, save_dir, page=page_obj.page,
                                                   progress_cb=progress_cb, progress=progress,
                                                   cache_dirs=cache_dirs, force=force)
                else:
                    result = self.download_video_with_audio(episode.bvid, save_dir, page=page_obj.page, quality=quality,
                                                            progress_cb=progress_cb, progress=progress,
                                                            cache_dirs=cache_dirs, force=force)
                new_results.append(result)
                success = True
            except DownloadCancelled:
                raise
            except DownloadError as exc:
                self._raise_if_cancelled()
                logger.error("视频 %s 第 %d 分P 下载失败，稍后重试：%s",
                             episode.bvid, page_obj.page, exc)
                failed_pages.append(page_obj.page)
            finally:
                progress.finish(success=success)
        return new_results, file_idx, failed_pages

    def _child_service(self, session) -> "VideoService":
        """创建并发子服务，继承权限换号候选、缓存与清晰度上限。"""
        return VideoService(
            session=session,
            default_dir=self.default_dir,
            cancel_event=getattr(self, "cancel_event", None),
            permission_accounts=self._permission_accounts_ref(),
            permission_cache=self._permission_cache_ref(),
            cap_non_vip_quality=getattr(self, "cap_non_vip_quality", None),
        )

    def _account_services(self, account_sessions=None, threads: int = 1) -> list:
        """为并发 worker 创建互不共享的 requests.Session。

        指定账号列表时按线程轮询账号，并为每个线程复制独立会话；这样并发数大于
        账号数时也不会多个线程同时操作同一个 Session。
        """
        threads = max(1, int(threads))
        if account_sessions:
            services = []
            for index in range(threads):
                source = account_sessions[index % len(account_sessions)]
                if isinstance(source, BiliSession):
                    session = BiliSession(cookie_path=source.cookie_path, referer=source.referer,
                                          max_retry=source.max_retry, timeout=source.timeout)
                    service = self._child_service(session)
                    service._owns_session = True
                else:
                    service = self._child_service(source)
                services.append(service)
            return services
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
            service = self._child_service(session)
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
        self._raise_if_cancelled()
        if media_type not in _ALLOWED_MEDIA_TYPES:
            raise ValueError(f"不支持的媒体类型：{media_type!r}，允许值：{sorted(_ALLOWED_MEDIA_TYPES)}")
        if season is None:
            season = self.fetch_season(bvid, season_id, mid)
        if season is None or not season.episodes:
            loc = f"bvid={bvid}" if bvid else f"season_id={season_id}"
            raise ValueError(f"{loc} 无法定位到合集，请确认参数正确。")

        season_dir = sanitize_filename(season.title)
        save_dir = (Path(dir) if dir is not None else self.default_dir) / season_dir
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
        retry_queue = []  # [(episode, failed_pages)]；failed_pages 为空表示整稿重试
        for i, episode in enumerate(season.episodes, 1):
            self._raise_if_cancelled()
            logger.info("合集「%s」下载：%s", season.title, episode.title)
            # 起始文件序号在闭包里固定：风控重试会重新执行整个动作，不能捕获到已更新的 file_idx
            start_idx = file_idx
            outcome = self._execute_batch_download(
                episode.bvid,
                lambda ep=episode, sidx=start_idx: self._download_episode(
                    ep, save_dir, media_type=media_type, quality=quality,
                    file_idx=sidx, progress=progress, progress_cb=progress_cb,
                    cache_dirs=cache_dirs, force=force,
                ),
                label=label,
            )
            page_count = len(episode.pages) if episode.is_multi_page else 1
            if outcome is _RETRY_OUTCOME:
                logger.info("视频 %s 下载失败，排到队尾重试（%s）。", episode.bvid, label)
                retry_queue.append((episode, []))
                file_idx += page_count
                continue
            if outcome is None:
                file_idx += page_count
                continue  # 视频不可见：_execute_batch_download 已记录日志
            new_results, file_idx, failed_pages = outcome
            results.extend(new_results)
            if failed_pages:
                logger.info("视频 %s 有 %d 个分P失败，排到队尾重试（%s）。",
                            episode.bvid, len(failed_pages), label)
                retry_queue.append((episode, failed_pages))
            download_count = self._report_bvid_download(
                episode.bvid, new_results, download_count, i, total,
            )
        if retry_queue:
            self._raise_if_cancelled()
            logger.info("合集「%s」有 %d 个稿件存在失败分P，开始最后重试。",
                        season.title, len(retry_queue))
            for episode, failed_pages in retry_queue:
                self._raise_if_cancelled()
                outcome = self._execute_batch_download(
                    episode.bvid,
                    lambda ep=episode, pages=failed_pages: self._download_all_pages_report(
                        ep.bvid, save_dir, quality=quality, media_type=media_type,
                        progress=progress, progress_cb=progress_cb,
                        cache_dirs=cache_dirs, force=force, only_pages=pages or None,
                    ),
                    label=label,
                )
                if outcome is _RETRY_OUTCOME or outcome is None:
                    logger.error("视频 %s 重试仍失败，跳过（%s）。", episode.bvid, label)
                    continue
                page_results, failed = outcome
                results.extend(page_results)
                if failed:
                    logger.error("视频 %s 的分P %s 重试仍失败，跳过（%s）。",
                                 episode.bvid, failed, label)
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
            if outcome is _RETRY_OUTCOME:
                logger.info("视频 %s 下载失败，排到队尾重试（%s）。",
                            season.episodes[index].bvid, label)
                return
            if outcome is None:
                return
            episode = season.episodes[index]
            new_results, _idx, failed_pages = outcome
            download_count = self._report_bvid_download(
                episode.bvid, new_results, download_count, completed_count, total,
            )
            if failed_pages:
                logger.info("视频 %s 有 %d 个分P失败，排到队尾重试（%s）。",
                            episode.bvid, len(failed_pages), label)

        outcomes = parallel_run(season.episodes, _work, threads, on_complete=_on_complete)
        # 下载结果仍按输入顺序返回；汇总日志已在每个任务完成时即时输出。
        results = []
        retry_queue = []  # [(episode, failed_pages)]
        for episode, outcome in zip(season.episodes, outcomes):
            if outcome is _RETRY_OUTCOME:
                retry_queue.append((episode, []))
            elif outcome is not None:
                new_results, _idx, failed_pages = outcome
                results.extend(new_results)
                if failed_pages:
                    retry_queue.append((episode, failed_pages))
        if retry_queue:
            self._raise_if_cancelled()
            logger.info("合集「%s」有 %d 个稿件存在失败分P，开始最后重试。",
                        season.title, len(retry_queue))
            for index, (episode, failed_pages) in enumerate(retry_queue):
                self._raise_if_cancelled()
                svc = services[index % len(services)]
                outcome = svc._execute_batch_download(
                    episode.bvid,
                    lambda ep=episode, pages=failed_pages: svc._download_all_pages_report(
                        ep.bvid, save_dir, quality=quality, media_type=media_type,
                        progress=progress, progress_cb=progress_cb,
                        cache_dirs=cache_dirs, force=force, only_pages=pages or None,
                    ),
                    label=label, risk_gate=gate,
                )
                if outcome is _RETRY_OUTCOME or outcome is None:
                    logger.error("视频 %s 重试仍失败，跳过（%s）。", episode.bvid, label)
                    continue
                page_results, failed = outcome
                results.extend(page_results)
                if failed:
                    logger.error("视频 %s 的分P %s 重试仍失败，跳过（%s）。",
                                 episode.bvid, failed, label)
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
        """统一执行收藏夹、UP 主等 BV 列表批量下载。

        单个视频下载失败（CDN 超时等）不会中断任务：先继续其余视频，全部结束后
        把失败项排到队尾统一重试一轮；仍失败则记录日志并跳过。
        """
        total = len(bvids)

        def run_item(service, bvid, risk_gate=None):
            def action():
                page_results, failed = service._download_all_pages_report(
                    bvid, save_dir, quality=quality, media_type=media_type,
                    progress=progress, progress_cb=progress_cb,
                    cache_dirs=cache_dirs, force=force,
                )
                if failed:
                    logger.error("视频 %s 有 %d 个分P下载失败，排到队尾重试（%s）。",
                                 bvid, len(failed), item_label(bvid))
                    return _RetryPages(bvid, failed, page_results)
                return page_results

            return service._execute_batch_download(
                bvid, action, label=item_label(bvid), risk_gate=risk_gate)

        def retry_item(service, item, risk_gate=None):
            """只重试失败的分P；pages 为空表示整个视频重试。"""
            def action():
                return service._download_all_pages_report(
                    item.bvid, save_dir, quality=quality, media_type=media_type,
                    progress=progress, progress_cb=progress_cb,
                    cache_dirs=cache_dirs, force=force,
                    only_pages=item.pages or None,
                )

            outcome = service._execute_batch_download(
                item.bvid, action, label=item_label(item.bvid), risk_gate=risk_gate)
            if outcome is None or outcome is _RETRY_OUTCOME:
                logger.error("视频 %s 重试仍失败，跳过（%s）。", item.bvid, item_label(item.bvid))
                return []
            page_results, failed = outcome
            if failed:
                logger.error("视频 %s 的分P %s 重试仍失败，跳过（%s）。",
                             item.bvid, failed, item_label(item.bvid))
            return page_results

        def handle_retry(service, item, results, download_count):
            page_results = retry_item(service, item)
            if not page_results:
                return download_count
            results.extend(page_results)
            return self._report_bvid_download(
                item.bvid, page_results, download_count, total, total)

        def collect_retry_item(bvid, outcome):
            if isinstance(outcome, _RetryPages):
                return outcome
            if outcome is _RETRY_OUTCOME:
                return _RetryPages(bvid)  # 整个视频重试（如取流阶段网络失败）
            return None

        if threads > 1:
            gate = RiskGate()
            services = self._account_services(account_sessions, threads)

            def work(bvid, index):
                service = services[index % len(services)]
                return run_item(service, bvid, risk_gate=gate)

            completed_count = 0
            download_count = 0

            def report_completion(index, outcome):
                nonlocal completed_count, download_count
                bvid = bvids[index]
                completed_count += 1
                if isinstance(outcome, _RetryPages) or outcome is _RETRY_OUTCOME:
                    return
                if outcome is None:
                    if on_skip is not None:
                        on_skip(bvid, completed_count, total)
                    return
                download_count = self._report_bvid_download(
                    bvid, outcome, download_count, completed_count, total,
                )

            try:
                outcomes = parallel_run(
                    bvids, work, threads, on_complete=report_completion,
                )
                results = []
                retry_items = []
                for bvid, outcome in zip(bvids, outcomes):
                    item = collect_retry_item(bvid, outcome)
                    if item is not None:
                        results.extend(item.results)
                        retry_items.append(item)
                    elif outcome is not None:
                        results.extend(outcome)
                if retry_items:
                    self._raise_if_cancelled()
                    logger.info("有 %d 个视频有失败分P，开始最后重试（%s）。",
                                len(retry_items), item_label(retry_items[0].bvid))
                    for i, item in enumerate(retry_items):
                        self._raise_if_cancelled()
                        service = services[i % len(services)]
                        download_count = handle_retry(
                            service, item, results, download_count)
                return results
            finally:
                self._close_owned_services(services)

        results = []
        download_count = 0
        retry_items = []
        for index, bvid in enumerate(bvids, 1):
            self._raise_if_cancelled()
            logger.info("%s：%s", item_label(bvid), bvid)
            outcome = run_item(self, bvid)
            item = collect_retry_item(bvid, outcome)
            if item is not None:
                results.extend(item.results)
                retry_items.append(item)
                continue
            if outcome is None:
                if on_skip is not None:
                    on_skip(bvid, index, total)
                continue
            results.extend(outcome)
            download_count = self._report_bvid_download(
                bvid, outcome, download_count, index, total,
            )
        if retry_items:
            self._raise_if_cancelled()
            logger.info("有 %d 个视频有失败分P，开始最后重试（%s）。",
                        len(retry_items), item_label(retry_items[0].bvid))
            for item in retry_items:
                self._raise_if_cancelled()
                download_count = handle_retry(self, item, results, download_count)
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
        self._raise_if_cancelled()
        from src.services.fav import FavService

        # 收藏夹链路：media_id -> 收藏夹详情（决定目录名）-> BV 列表 ->
        # 对每个 BV 复用普通视频下载流程；GUI 传入 bvids 时可避免重复拉列表。
        fav = FavService(self.session)
        info = fav.get_fav_info(fid)
        if bvids is None:
            bvids = fav.get_fav_bv(fid)
        if not bvids:
            raise ValueError(f"收藏夹「{info.title}」没有视频。")

        fav_dir = sanitize_filename(info.title)
        save_dir = (Path(dir) if dir is not None else self.default_dir) / fav_dir
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
                f"跳过视频 {bvid}，进度 {index}/{count}"
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

        空间“投稿”列表包含该 UP 主作为嘉宾参与的**他人联合投稿**；这些稿件
        不是该 UP 主自己的投稿，但仍会一并返回（与 B 站空间页面一致），
        并在日志中标注，便于核对下载范围。

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
        others = []  # 他人稿件：该 UP 主只是联合投稿里的嘉宾
        pn = 1
        while True:
            self._raise_if_cancelled()
            params = {"mid": mid, "pn": pn, "ps": ps, "order": "pubdate"}
            get_wbi(params)  # 原地追加 wts 与 w_rid
            data = self.session.get(UserUrls.SPACE_ARC_SEARCH, params=params)
            vlist = data.get("list", {}).get("vlist", [])
            for video in vlist:
                bvid = video.get("bvid")
                if not bvid:
                    continue
                bvids.append(bvid)
                owner_mid = video.get("mid")
                if owner_mid is not None and owner_mid != mid:
                    others.append((bvid, video.get("author") or str(owner_mid)))
            total = data.get("page", {}).get("count", 0)
            if len(bvids) >= total or not vlist:
                break
            pn += 1
            time.sleep(0.3)  # 避免风控
        if others:
            logger.info(
                "UP主 %s 空间共 %d 条视频，其中 %d 条为他人稿件（该UP主仅为联合投稿嘉宾，将一并下载）。",
                mid, len(bvids), len(others))
            for bvid, author in others:
                logger.info("  他人稿件：%s（UP主：%s）", bvid, author)
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
        self._raise_if_cancelled()
        from src.services.user import UserService

        # UP 主链路：规范化 mid -> 空间投稿分页得到 BV 列表 -> 查询昵称作为
        # 输出目录 -> 每个 BV 进入 download_all_pages；列表可由 GUI 预取后传入。
        mid = self._resolve_mid(mid)
        if bvids is None:
            bvids = self.list_up_videos(mid)
        if not bvids:
            raise ValueError(f"UP主 {mid} 没有视频。")

        up_name = UserService(self.session).get_name(mid) or f"up_{mid}"
        up_dir = sanitize_filename(up_name)
        save_dir = (Path(dir) if dir is not None else self.default_dir) / up_dir
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
        )

