"""下载线程：每个任务一个 QThread，内部自建 VideoService（独立会话）。"""
import logging
import time
import threading
from collections.abc import Mapping

from PySide6.QtCore import QThread, Signal

from src.services.dressup import DressupService
from src.services.emote import EmoteService
from src.services.fav import FavService
from src.services.garb import GarbService
from src.services.video import VideoService
from src.api.errors import BiliAuthError, BiliRiskError
from src.models.download_request import DownloadRequest, DownloadSource, MediaType

from frontend.pyside6.signals import LogCategory, app_signals
from frontend.pyside6.utils import resolve_input
from frontend.pyside6.workers.progress_adapter import ProgressAdapter

logger = logging.getLogger(__name__)

# 错误类别：manager 据此决定是否重检登录
ERROR_NONE = 0
ERROR_AUTH = 1
ERROR_RISK = 2
ERROR_OTHER = 3


class DownloadWorker(QThread):
    progress = Signal(int, int)       # done, total（字节）
    phase = Signal(str)               # 阶段文本（如 ffmpeg 合成中）
    done = Signal(bool, str, int)     # (success, summary, error_kind)

    def __init__(self, spec: DownloadRequest | Mapping, parent=None):
        super().__init__(parent)
        self.request = DownloadRequest.from_legacy_dict(spec)
        self._service = None
        self._owned_account_sessions = []
        self._cancel_event = threading.Event()

    @property
    def spec(self) -> dict:
        """兼容旧调用方读取任务字典。内部逻辑统一使用 ``request``。"""
        return self.request.to_legacy_dict()

    def cancel(self) -> None:
        self._cancel_event.set()
        self.requestInterruption()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set() or self.isInterruptionRequested()

    def milestone(self, category: int, text: str) -> None:
        app_signals.log_message.emit(category, text)

    def _resolve_pending(self):
        """短链等输入在工作线程内跟随跳转解析，避免阻塞界面线程。"""
        request = self.request
        if not request.pending_resolve:
            return
        raw = request.input_value
        source = request.source.value
        canonical = resolve_input(source, raw)
        display = self._canonical_display(source, canonical)
        description = f"{self._source_label(source)}（已解析：{display}）"
        self.request = request.with_resolved_input(canonical, description)
        self.milestone(LogCategory.NORMAL, f"解析链接：{raw} → {display}")
        self.phase.emit(f"已解析：{display}")

    @staticmethod
    def _source_label(source: str) -> str:
        return {
            "bv": "视频", "fav": "收藏夹", "season": "合集", "up": "UP主",
            "emote": "表情包", "garb": "收藏集/装扮", "dressup": "装扮",
        }.get(source, source)

    @staticmethod
    def _canonical_display(source: str, canonical) -> str:
        # season 规范值为 (kind, val, mid)，显示 val（合集 id）；其余直接显示
        return str(canonical[1]) if source == "season" else str(canonical)

    def run(self):
        # worker 是 GUI 到 SDK 的数据流汇合点：spec（来源/规范 id/选项）
        # -> service API -> DownloadResult -> Qt 信号；所有异常在这里转换成可读摘要。
        result_payload = None
        try:
            started_at = time.perf_counter()
            service = VideoService(cancel_event=self._cancel_event)
            self._service = service
            self._resolve_pending()
            self.milestone(LogCategory.NORMAL, f"开始任务：{self.request.description}")
            results = self._execute(service)
            summary = self._summary(results, time.perf_counter() - started_at)
            # 单文件任务的完成里程碑由 ProgressAdapter.finish() 输出（"下载完成/已存在"），
            # 这里只为批量任务额外输出一条汇总。
            if isinstance(results, list):
                self.milestone(LogCategory.SUCCESS, summary)
            result_payload = (True, summary, ERROR_NONE)
        except Exception as e:
            kind = self._error_kind(e)
            text = self._error_text(e)
            logger.exception("[DownloadWorker] 任务失败：%s", self.request.description)
            self.milestone(LogCategory.ERROR, f"下载失败：{text}")
            result_payload = (False, text, kind)
        finally:
            for session in self._owned_account_sessions:
                try:
                    session.close()
                except Exception:
                    logger.warning("关闭账号下载会话失败", exc_info=True)
            self._owned_account_sessions.clear()
            if self._service is not None:
                try:
                    self._service.session.close()
                except Exception:
                    logger.warning("关闭下载会话失败", exc_info=True)
            # 必须在所有会话和资源清理完成后再通知 manager。否则 manager/UI 可能
            # 在 QThread.finished 之前释放最后一个 worker 引用，触发 Qt 的致命退出。
            if result_payload is not None:
                self.done.emit(*result_payload)

    # ---- 下载执行 ----

    def _execute(self, service):
        handlers = {
            DownloadSource.VIDEO: self._execute_video,
            DownloadSource.FAVORITE: self._execute_favorite,
            DownloadSource.SEASON: self._execute_season,
            DownloadSource.UPLOADER: self._execute_uploader,
            DownloadSource.EMOTE: self._execute_emote,
            DownloadSource.GARB: self._execute_garb,
            DownloadSource.DRESSUP: self._execute_dressup,
        }
        handler = handlers.get(self.request.source)
        if handler is None:
            raise ValueError(f"未知下载来源：{self.request.source.value}")
        return handler(service)

    def _execute_video(self, service):
        request = self.request
        bvid = request.input_value
        if request.scope == "single":
            adapter = ProgressAdapter(1, f"视频 {bvid}", self)
            adapter.start(1, f"{bvid}（P{request.page}）")
            if request.media_type == MediaType.AUDIO:
                result = service.download_audio(
                    bvid, request.save_dir, page=request.page, progress=adapter,
                    cache_dirs=list(request.cache_dirs), force=request.force,
                )
            else:
                result = service.download_video_with_audio(
                    bvid, request.save_dir, page=request.page, quality=request.quality,
                    progress=adapter, cache_dirs=list(request.cache_dirs), force=request.force,
                )
            adapter.finish()
            return result
        info = service.fetch_info(bvid)
        page_count = len(info.pages) if info.pages else 1
        adapter = ProgressAdapter(page_count, f"视频 {bvid}", self)
        return service.download_all_pages(
            bvid, request.save_dir, quality=request.quality,
            media_type=self._video_media_type(request), progress=adapter,
            cache_dirs=list(request.cache_dirs), force=request.force,
        )

    def _execute_favorite(self, service):
        request = self.request
        favorite_id = request.input_value
        bvids = FavService(service.session).get_fav_bv(favorite_id)
        adapter = self._make_adapter(request.threads, len(bvids), f"收藏夹 {favorite_id}")
        return service.download_fav(
            favorite_id, request.save_dir,
            mode=self._download_mode(request), quality=request.quality,
            progress=adapter, bvids=bvids, threads=request.threads,
            account_sessions=self._account_sessions(request),
            cache_dirs=list(request.cache_dirs), force=request.force,
        )

    def _execute_season(self, service):
        request = self.request
        kind, value, mid = request.input_value
        if kind == "bvid":
            season = service.fetch_season(bvid=value)
            bvid, season_id = value, None
        else:
            season = service.fetch_season(season_id=value, mid=mid)
            bvid, season_id = None, value
        if season is None or not season.episodes:
            raise ValueError("无法定位到合集，请确认参数正确")
        file_count = sum(
            len(episode.pages) if episode.is_multi_page else 1
            for episode in season.episodes
        )
        adapter = self._make_adapter(request.threads, file_count, f"合集「{season.title}」")
        return service.download_season(
            bvid=bvid, dir=request.save_dir, season_id=season_id, mid=mid or 0,
            quality=request.quality, media_type=self._video_media_type(request),
            progress=adapter, season=season, threads=request.threads,
            account_sessions=self._account_sessions(request),
            cache_dirs=list(request.cache_dirs), force=request.force,
        )

    def _execute_emote(self, service):
        request = self.request
        package_ids = request.input_value
        emote_service = EmoteService(service.session)
        packages, count = emote_service.count_emotes(package_ids)
        adapter = ProgressAdapter(count, f"表情包 {','.join(map(str, package_ids))}", self)
        return emote_service.download_packages(
            package_ids, request.save_dir, progress=adapter, packages=packages,
            use_full_name=request.emote_full_name,
        )

    def _execute_dressup(self, service):
        request = self.request
        items = request.input_value
        if not isinstance(items, list) or not items:
            raise ValueError("未选择要下载的装扮/表情包")
        dressup_service = DressupService(service.session)
        adapter = self._make_adapter(request.threads, len(items), f"装扮 {len(items)} 项")
        return dressup_service.download_items(
            items, request.save_dir, threads=request.threads,
            account_sessions=self._account_sessions(request), progress=adapter,
            use_full_name=request.emote_full_name,
        )

    def _execute_garb(self, service):
        request = self.request
        garb_service = GarbService(service.session)
        item, detail, count = garb_service.prepare_download(request.input_value)
        adapter = ProgressAdapter(
            count, f"收藏集/装扮 {item.get('name') or request.input_value}", self
        )
        return garb_service.download_item(
            item, request.save_dir, detail=detail, progress=adapter,
        )

    def _execute_uploader(self, service):
        request = self.request
        bvids = service.list_up_videos(request.input_value)
        adapter = self._make_adapter(request.threads, len(bvids), f"UP主 {request.input_value}")
        return service.download_up(
            request.input_value, request.save_dir,
            mode=self._download_mode(request), quality=request.quality,
            progress=adapter, bvids=bvids, threads=request.threads,
            account_sessions=self._account_sessions(request),
            cache_dirs=list(request.cache_dirs), force=request.force,
        )

    @staticmethod
    def _video_media_type(request: DownloadRequest) -> str:
        return "audio" if request.media_type == MediaType.AUDIO else "video_with_audio"

    @staticmethod
    def _download_mode(request: DownloadRequest) -> str:
        return "audio" if request.media_type == MediaType.AUDIO else "video"

    def _account_sessions(self, request: DownloadRequest):
        """多账号分流：并发且开启分流时，为每个登录有效的账号建一个独立 BiliSession。

        :return: BiliSession 列表；未开启或没有可用账号时返回 None（沿用当前账号）
        """
        if request.threads <= 1 or not request.distribute_accounts:
            return None
        try:
            from src.api.session import BiliSession
            from src.config.cookie import BiliCookies
            from src.services.account import AccountManager
        except Exception:
            return None
        sessions = []
        for acc in AccountManager().list_accounts():
            try:
                cookies = BiliCookies.from_file(acc.cookie_path)
            except FileNotFoundError:
                continue
            if cookies.has_valid_session:
                sessions.append(BiliSession(cookie_path=str(acc.cookie_path)))
        if sessions:
            self._owned_account_sessions.extend(sessions)
        return sessions or None

    def _make_adapter(self, threads, n, label):
        """并发（threads>1）时用线程安全的 ParallelProgressAdapter，否则用普通 ProgressAdapter。"""
        if threads > 1:
            from frontend.pyside6.workers.progress_adapter import ParallelProgressAdapter
            return ParallelProgressAdapter(n, label, self)
        return ProgressAdapter(n, label, self)

    def _summary(self, results, elapsed: float | None = None) -> str:
        if results is None:
            summary = "任务完成：无结果"
        elif isinstance(results, list):
            cached = sum(1 for r in results if getattr(r, "cached", False))
            summary = f"任务完成：共 {len(results)} 个文件（其中缓存 {cached} 个）"
        elif getattr(results, "cached", False):
            return f"已存在，跳过下载：{results.path}"
        else:
            return f"下载完成：{results.path}"

        if elapsed is not None:
            summary += f"，用时 {elapsed:.2f} 秒"
        return summary

    def _error_kind(self, e) -> int:
        if isinstance(e, BiliAuthError):
            return ERROR_AUTH
        if isinstance(e, BiliRiskError):
            return ERROR_RISK
        return ERROR_OTHER

    def _error_text(self, e) -> str:
        return str(e) or e.__class__.__name__
