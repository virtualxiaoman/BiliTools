"""下载任务管理：登录门禁 + 去重 + 并发（每次提交一个新线程）。

- 未登录 → 阻止并引导去登录页；
- 相同任务（参数完全一致）已在运行/排队 → 不重复提交；
- 内容变化（参数不同）→ 立即新开线程并发下载。
"""
from functools import partial
from typing import Optional

from PySide6.QtCore import QObject, Signal

from frontend.pyside6.signals import LogCategory, app_signals
from frontend.pyside6.utils import has_valid_session
from frontend.pyside6.workers.download_worker import ERROR_AUTH, DownloadWorker


class DownloadManager(QObject):
    task_started = Signal(int, str)         # id, desc
    task_progress = Signal(int, int, int)   # id, done, total（字节）
    task_phase = Signal(int, str)           # id, phase
    task_finished = Signal(int, bool, str)  # id, success, summary
    count_changed = Signal(int)             # 运行中任务数

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks = {}        # id -> worker
        self._keys = {}         # key -> id
        self._key_by_tid = {}   # id -> key
        self._next_id = 1

    def has_running(self) -> bool:
        return bool(self._tasks)

    def shutdown(self, wait_ms: int = 2000) -> None:
        """应用退出前停止所有下载线程（尽力而为）。

        - 先请求中断并短暂等待；
        - 仍阻塞（下载/ffmpeg 是同步阻塞调用，无法协作中断）则 terminate 兜底。
        文件按块写入且支持断点续传，中断不会损坏已有数据。
        """
        for worker in list(self._tasks.values()):
            try:
                worker.requestInterruption()
            except Exception:
                pass
        for worker in list(self._tasks.values()):
            try:
                if worker.isRunning() and not worker.wait(wait_ms):
                    worker.terminate()
                    worker.wait(1000)
            except Exception:
                pass

    def submit(self, spec: dict) -> Optional[int]:
        if not has_valid_session():
            app_signals.log_message.emit(LogCategory.WARN, "未登录，无法下载，请先扫码登录")
            app_signals.goto_page.emit("login")
            return None

        key = self._make_key(spec)
        if key in self._keys:
            app_signals.log_message.emit(
                LogCategory.PROGRESS, f"相同任务已在进行，不重复提交：{spec['desc']}"
            )
            return None

        worker = DownloadWorker(spec)
        tid = self._next_id
        self._next_id += 1
        worker.progress.connect(partial(self._on_progress, tid))
        worker.phase.connect(partial(self._on_phase, tid))
        worker.done.connect(partial(self._on_done, tid))
        self._tasks[tid] = worker
        self._keys[key] = tid
        self._key_by_tid[tid] = key

        self.task_started.emit(tid, spec["desc"])
        self.count_changed.emit(len(self._tasks))
        worker.start()
        return tid

    def _on_progress(self, tid, done, total):
        self.task_progress.emit(tid, done, total)

    def _on_phase(self, tid, text):
        self.task_phase.emit(tid, text)

    def _on_done(self, tid, success, summary, errkind):
        self._tasks.pop(tid, None)
        key = self._key_by_tid.pop(tid, None)
        if key is not None:
            self._keys.pop(key, None)
        self.task_finished.emit(tid, success, summary)
        self.count_changed.emit(len(self._tasks))
        if errkind == ERROR_AUTH:
            app_signals.log_message.emit(LogCategory.ERROR, "下载失败可能由登录失效引起，请重新登录后重试")
            app_signals.login_changed.emit(None)
            app_signals.goto_page.emit("login")

    def _make_key(self, spec) -> tuple:
        return (
            spec["source"],
            repr(spec["input"]),
            spec.get("scope", "all"),
            spec.get("page", 1),
            spec["media_type"],
            int(spec["quality"]),
            str(spec["save_dir"]),
        )
