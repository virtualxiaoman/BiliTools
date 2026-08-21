"""装扮搜索线程：后台同时搜索表情包、收藏集与主题装扮。"""

from PySide6.QtCore import QThread, Signal

from src.services.dressup import DressupService


_keepalive = []


class DressupSearchWorker(QThread):
    """一次关键词搜索。结果以 dict 列表回传（含 kind/name/display_name/payload）。"""

    results = Signal(list)
    failed = Signal(str)

    def __init__(self, keyword: str, parent=None):
        super().__init__(parent)
        self.keyword = keyword
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self):
        if self._stop:
            return
        try:
            service = DressupService()
            items = service.search(self.keyword)
            self.results.emit([item.as_dict() for item in items])
        except Exception as e:
            self.failed.emit(str(e) or e.__class__.__name__)


def search_dressup(keyword: str, on_results, on_error) -> DressupSearchWorker:
    """启动一次后台搜索，结果/错误通过回调送达主线程。"""
    worker = DressupSearchWorker(keyword)
    worker.results.connect(on_results)
    worker.failed.connect(on_error)
    worker.finished.connect(lambda: _drop(worker))
    _keepalive.append(worker)
    worker.start()
    return worker


def shutdown_all() -> None:
    """应用退出前停止装扮搜索线程（尽力而为，避免后台 QThread 残留）。"""
    for worker in list(_keepalive):
        try:
            worker.stop()
            if worker.isRunning():
                worker.wait(2000)
        except Exception:
            pass
        _drop(worker)


def _drop(worker) -> None:
    if worker in _keepalive:
        _keepalive.remove(worker)
