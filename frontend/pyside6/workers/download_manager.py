"""下载任务管理：登录门禁 + 去重 + 并发（每次提交一个新线程）。

- 未登录 → 阻止并引导去登录页；
- 相同任务（参数完全一致）已在运行/排队 → 不重复提交；
- 内容变化（参数不同）→ 立即新开线程并发下载。
"""
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal, Slot

from frontend.pyside6.signals import LogCategory, app_signals
from frontend.pyside6.utils import has_valid_session
from frontend.pyside6.workers.download_worker import ERROR_AUTH, DownloadWorker
from src.models.download_request import DownloadRequest, DownloadSource

logger = logging.getLogger(__name__)


@dataclass
class TaskRecord:
    """任务生命周期内的唯一状态记录。"""

    task_id: int
    deduplication_key: tuple
    worker: DownloadWorker
    done_emitted: bool = False


class DownloadManager(QObject):
    task_started = Signal(int, str)         # id, desc
    task_progress = Signal(int, int, int)   # id, done, total（字节）
    task_phase = Signal(int, str)           # id, phase
    task_finished = Signal(int, bool, str)  # id, success, summary
    count_changed = Signal(int)             # 运行中任务数

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: dict[int, TaskRecord] = {}
        self._task_id_by_key: dict[tuple, int] = {}
        self._next_id = 1

    def has_running(self) -> bool:
        return bool(self._tasks)

    def shutdown(self, wait_ms: int = 2000) -> bool:
        """请求协作式取消并等待线程退出；不使用 ``terminate``，避免破坏文件和 Python 状态。

        返回 ``False`` 表示仍有线程运行。调用方此时必须阻止窗口/应用销毁，
        否则 QThread Python/C++ 对象可能在线程仍运行时被回收，触发 Qt 致命退出。
        """
        workers = [record.worker for record in self._tasks.values()]
        for worker in workers:
            try:
                worker.cancel()
            except Exception:
                logger.exception("请求下载任务取消失败")
        deadline = time.monotonic() + max(wait_ms, 0) / 1000
        for worker in workers:
            try:
                if not worker.isRunning():
                    continue
                remaining = max(0, int((deadline - time.monotonic()) * 1000))
                if not worker.wait(remaining):
                    logger.error(
                        "下载线程未能在退出期限内结束：%s",
                        self._worker_description(worker),
                    )
            except Exception:
                logger.exception("等待下载线程退出失败")
        running = [record.worker for record in self._tasks.values() if record.worker.isRunning()]
        return not running

    def submit(self, spec: DownloadRequest | Mapping) -> Optional[int]:
        request = DownloadRequest.from_legacy_dict(spec)
        # 装扮/表情包详情与 CDN 资源可匿名访问；其余视频下载仍要求有效登录。
        if request.source not in {
            DownloadSource.EMOTE,
            DownloadSource.GARB,
            DownloadSource.DRESSUP,
        } and not has_valid_session():
            app_signals.log_message.emit(LogCategory.WARN, "未登录，无法下载，请先扫码登录")
            app_signals.goto_page.emit("login")
            return None

        # 面板已经把输入转换为规范 spec；manager 在启动线程前只做门禁和去重，
        # 真正的网络解析、API 调用和下载全部放到 DownloadWorker，避免阻塞 Qt 主线程。
        key = request.deduplication_key()
        if key in self._task_id_by_key:
            app_signals.log_message.emit(
                LogCategory.PROGRESS,
                f"相同任务已在进行，不重复提交：{request.description}",
            )
            return None

        # 一个任务对应一个 QThread，信号只传递进度/阶段/完成摘要；
        # manager 不直接触碰 BiliSession 或媒体文件，保持 UI 调度与后端执行解耦。
        worker = DownloadWorker(request)
        tid = self._next_id
        self._next_id += 1
        # 不使用 partial 作为槽：它没有稳定的 QObject 线程归属，可能直接在
        # QThread 工作线程中修改 manager 的字典并触发 UI 信号。使用 manager
        # 的真实 Qt Slot + QueuedConnection，所有状态变更统一回到 GUI 线程。
        worker._download_task_id = tid
        worker.progress.connect(self._on_worker_progress, Qt.ConnectionType.QueuedConnection)
        worker.phase.connect(self._on_worker_phase, Qt.ConnectionType.QueuedConnection)
        worker.done.connect(self._on_worker_done, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self._on_worker_finished, Qt.ConnectionType.QueuedConnection)
        self._tasks[tid] = TaskRecord(tid, key, worker)
        self._task_id_by_key[key] = tid

        self.task_started.emit(tid, request.description)
        self.count_changed.emit(len(self._tasks))
        worker.start()
        return tid

    @staticmethod
    def _sender_task_id(sender) -> Optional[int]:
        return getattr(sender, "_download_task_id", None) if sender is not None else None

    @Slot(int, int)
    def _on_worker_progress(self, done, total):
        tid = self._sender_task_id(self.sender())
        if tid is not None:
            self.task_progress.emit(tid, done, total)

    @Slot(str)
    def _on_worker_phase(self, text):
        tid = self._sender_task_id(self.sender())
        if tid is not None:
            self.task_phase.emit(tid, text)

    @Slot(bool, str, int)
    def _on_worker_done(self, success, summary, errkind):
        worker = self.sender()
        tid = self._sender_task_id(worker)
        record = self._tasks.get(tid) if tid is not None else None
        if record is None:
            return
        if record.done_emitted:
            return
        record.done_emitted = True
        # 这里只报告任务完成，不释放 worker。QThread.run() 可能仍在执行 finally
        # 或清理 Python/requests 资源，必须等 finished 信号后再删除强引用。
        self.task_finished.emit(tid, success, summary)
        if errkind == ERROR_AUTH:
            app_signals.log_message.emit(LogCategory.ERROR, "下载失败可能由登录失效引起，请重新登录后重试")
            app_signals.login_changed.emit(None)
            app_signals.goto_page.emit("login")

    @Slot()
    def _on_worker_finished(self):
        worker = self.sender()
        tid = self._sender_task_id(worker)
        record = self._tasks.get(tid) if tid is not None else None
        if record is None:
            return
        # 极端情况下 run() 未能发出 done；不能让 UI 永久显示运行中。
        if not record.done_emitted:
            record.done_emitted = True
            self.task_finished.emit(tid, False, "下载线程异常退出")
        self._tasks.pop(tid, None)
        self._task_id_by_key.pop(record.deduplication_key, None)
        self.count_changed.emit(len(self._tasks))
        if worker is not None:
            worker.deleteLater()

    def _make_key(self, spec) -> tuple:
        return DownloadRequest.from_legacy_dict(spec).deduplication_key()

    @staticmethod
    def _worker_description(worker) -> str:
        request = getattr(worker, "request", None)
        if request is not None:
            return request.description
        spec = getattr(worker, "spec", {})
        return spec.get("desc", "") if isinstance(spec, Mapping) else ""
