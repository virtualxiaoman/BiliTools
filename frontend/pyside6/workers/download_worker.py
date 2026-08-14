"""下载线程：每个任务一个 QThread，内部自建 VideoService（独立会话）。"""
import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from src.services.fav import FavService
from src.services.video import VideoService
from src.api.errors import BiliAuthError, BiliRiskError

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

    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self.spec = spec
        self._service = None

    def milestone(self, category: int, text: str) -> None:
        app_signals.log_message.emit(category, text)

    def _resolve_pending(self):
        """短链等输入在工作线程内跟随跳转解析，避免阻塞界面线程。"""
        if not self.spec.get("pending_resolve"):
            return
        raw = self.spec["input"]
        source = self.spec["source"]
        canonical = resolve_input(source, raw)
        self.spec["input"] = canonical
        self.spec["pending_resolve"] = False
        display = self._canonical_display(source, canonical)
        self.spec["desc"] = f"{self._source_label(source)}（已解析：{display}）"
        self.milestone(LogCategory.NORMAL, f"解析链接：{raw} → {display}")
        self.phase.emit(f"已解析：{display}")

    @staticmethod
    def _source_label(source: str) -> str:
        return {"bv": "视频", "fav": "收藏夹", "season": "合集", "up": "UP主"}.get(source, source)

    @staticmethod
    def _canonical_display(source: str, canonical) -> str:
        # season 规范值为 (kind, val, mid)，显示 val（合集 id）；其余直接显示
        return str(canonical[1]) if source == "season" else str(canonical)

    def run(self):
        try:
            service = VideoService()
            self._service = service
            self._resolve_pending()
            self.milestone(LogCategory.NORMAL, f"开始任务：{self.spec['desc']}")
            results = self._execute(service)
            summary = self._summary(results)
            # 单文件任务的完成里程碑由 ProgressAdapter.finish() 输出（"下载完成/已存在"），
            # 这里只为批量任务额外输出一条汇总。
            if isinstance(results, list):
                self.milestone(LogCategory.SUCCESS, summary)
            self.done.emit(True, summary, ERROR_NONE)
        except Exception as e:
            kind = self._error_kind(e)
            text = self._error_text(e)
            logger.exception("[DownloadWorker] 任务失败：%s", self.spec.get("desc"))
            self.milestone(LogCategory.ERROR, f"下载失败：{text}")
            self.done.emit(False, text, kind)

    # ---- 下载执行 ----

    def _execute(self, service):
        spec = self.spec
        save_dir = Path(spec["save_dir"])
        quality = spec["quality"]
        mt = spec["media_type"]
        src = spec["source"]
        media_type = "audio" if mt == "audio" else "video_with_audio"

        if src == "bv":
            bvid = spec["input"]
            if spec["scope"] == "single":
                adapter = ProgressAdapter(1, f"视频 {bvid}", self)
                page = spec["page"]
                adapter.start(1, f"{bvid}（P{page}）")
                if mt == "audio":
                    result = service.download_audio(bvid, save_dir, page=page, progress=adapter)
                else:
                    result = service.download_video_with_audio(
                        bvid, save_dir, page=page, quality=quality, progress=adapter
                    )
                adapter.finish()
                return result
            info = service.fetch_info(bvid)
            n = len(info.pages) if info.pages else 1
            adapter = ProgressAdapter(n, f"视频 {bvid}", self)
            return service.download_all_pages(
                bvid, save_dir, quality=quality, media_type=media_type, progress=adapter
            )

        if src == "fav":
            fid = spec["input"]
            # 先取一次收藏夹视频列表：既用于进度总数，也传回 service 复用，避免内部再拉取一次
            bvids = FavService(service.session).get_fav_bv(fid)
            adapter = ProgressAdapter(len(bvids), f"收藏夹 {fid}", self)
            mode = "audio" if mt == "audio" else "video"
            return service.download_fav(fid, save_dir, mode=mode, quality=quality,
                                        progress=adapter, bvids=bvids)

        if src == "season":
            kind, val, mid = spec["input"]
            if kind == "bvid":
                season = service.fetch_season(bvid=val)
                bvid, season_id = val, None
            else:
                season = service.fetch_season(season_id=val, mid=mid)
                bvid, season_id = None, val
            if season is None or not season.episodes:
                raise ValueError("无法定位到合集，请确认参数正确")
            file_count = sum(len(ep.pages) if ep.is_multi_page else 1 for ep in season.episodes)
            adapter = ProgressAdapter(file_count, f"合集「{season.title}」", self)
            return service.download_season(
                bvid=bvid, dir=save_dir, season_id=season_id, mid=mid or 0,
                quality=quality, media_type=media_type, progress=adapter, season=season,
            )

        if src == "up":
            mid = spec["input"]
            # 先取一次 UP 主视频列表：既用于进度总数，也传回 service 复用，避免内部再翻页一次
            bvids = service.list_up_videos(mid)
            adapter = ProgressAdapter(len(bvids), f"UP主 {mid}", self)
            mode = "audio" if mt == "audio" else "video"
            return service.download_up(mid, save_dir, mode=mode, quality=quality,
                                       progress=adapter, bvids=bvids)

        raise ValueError(f"未知下载来源：{src}")

    def _summary(self, results) -> str:
        if results is None:
            return "任务完成：无结果"
        if isinstance(results, list):
            cached = sum(1 for r in results if getattr(r, "cached", False))
            return f"任务完成：共 {len(results)} 个文件（其中缓存 {cached} 个）"
        if getattr(results, "cached", False):
            return f"已存在，跳过下载：{results.path}"
        return f"下载完成：{results.path}"

    def _error_kind(self, e) -> int:
        if isinstance(e, BiliAuthError):
            return ERROR_AUTH
        if isinstance(e, BiliRiskError):
            return ERROR_RISK
        return ERROR_OTHER

    def _error_text(self, e) -> str:
        return str(e) or e.__class__.__name__
