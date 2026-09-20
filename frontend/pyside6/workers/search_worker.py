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




class DirectDressupImportWorker(QThread):
    """后台校验按 ID 导入的收藏集或主题装扮。"""

    result = Signal(dict)
    failed = Signal(str)

    def __init__(self, *, act_id=None, lottery_id=None, item_id=None, parent=None):
        super().__init__(parent)
        self.act_id = act_id
        self.lottery_id = lottery_id
        self.item_id = item_id
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self):
        if self._stop:
            return
        try:
            item = DressupService().import_by_ids(
                act_id=self.act_id, lottery_id=self.lottery_id, item_id=self.item_id,
            )
            if not self._stop:
                self.result.emit(item.as_dict())
        except Exception as exc:
            if not self._stop:
                self.failed.emit(str(exc) or exc.__class__.__name__)


def import_dressup_by_ids(*, act_id=None, lottery_id=None, item_id=None, on_result, on_error) -> DirectDressupImportWorker:
    """启动按 ID 导入的详情校验线程。"""
    worker = DirectDressupImportWorker(act_id=act_id, lottery_id=lottery_id, item_id=item_id)
    worker.result.connect(on_result)
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
