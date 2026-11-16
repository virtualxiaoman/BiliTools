"""DownloadManager/QThread 生命周期回归测试。"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication

import frontend.pyside6.workers.download_manager as manager_module


class _FakeWorker(QThread):
    progress = Signal("qint64", "qint64")
    phase = Signal(str)
    done = Signal(bool, str, int)

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec

    def cancel(self):
        pass

    def run(self):
        # 模拟真实 worker：done 发生在 run 返回前，finished 随后才发出。
        self.done.emit(True, "下载完成", 0)
        time.sleep(0.03)


def test_worker_is_retained_until_qthread_finished(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(manager_module, "DownloadWorker", _FakeWorker)
    monkeypatch.setattr(manager_module, "has_valid_session", lambda: True)

    manager = manager_module.DownloadManager()
    observed_task_counts = []
    manager.task_finished.connect(lambda *_: observed_task_counts.append(len(manager._tasks)))
    spec = {
        "source": "fav",
        "input": 1,
        "scope": "all",
        "page": 1,
        "media_type": "video_with_audio",
        "quality": 120,
        "save_dir": "output/video",
        "desc": "收藏夹测试",
    }

    assert manager.submit(spec) == 1
    deadline = time.monotonic() + 2
    while manager.has_running() and time.monotonic() < deadline:
        app.processEvents()
        QThread.msleep(1)
    app.processEvents()

    assert observed_task_counts == [1]
    assert not manager.has_running()


def test_progress_signals_accept_over_2gb_bytes():
    """并发下载总字节数会超过 2GB，进度信号必须按 64 位传递。"""
    from frontend.pyside6.workers.download_worker import DownloadWorker

    app = QApplication.instance() or QApplication([])
    big = 2**31 + 12345

    worker = DownloadWorker({
        "source": "bv", "input": "BV1ov42117yC", "scope": "all", "page": 1,
        "save_dir": ".", "desc": "溢出测试",
    })
    worker_progress = []
    worker.progress.connect(lambda done, total: worker_progress.append((done, total)))
    worker.progress.emit(big, big + 100)

    manager = manager_module.DownloadManager()
    manager_progress = []
    manager.task_progress.connect(
        lambda tid, done, total: manager_progress.append((tid, done, total))
    )
    manager.task_progress.emit(1, big, big + 100)
    app.processEvents()

    assert worker_progress == [(big, big + 100)]
    assert manager_progress == [(1, big, big + 100)]
