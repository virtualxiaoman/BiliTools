"""装扮页签 UI 行为测试（离屏 Qt）：勾选、全选、选中列表。"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from frontend.pyside6.signals import LogCategory, app_signals
from frontend.pyside6.widgets.dressup_panel import DressupPanel
from frontend.pyside6.widgets.download_panel import DownloadPanel


def _items():
    return [
        {"kind": "emoji", "name": "表情包A", "display_name": "表情包-表情包A", "payload": {"id": 1}},
        {"kind": "collection", "name": "收藏集A", "display_name": "收藏集-收藏集A", "payload": {"name": "收藏集A"}},
        {"kind": "suit", "name": "装扮B", "display_name": "装扮-装扮B", "payload": {"item_id": 2}},
    ]


def test_dressup_panel_search_input_is_single_line_height():
    app = QApplication.instance() or QApplication([])
    panel = DressupPanel()
    assert panel.input.maximumHeight() == 34
    assert panel.input.minimumHeight() == 34


def test_dressup_panel_select_all_toggle():
    app = QApplication.instance() or QApplication([])
    panel = DressupPanel()
    panel._on_results(_items())

    assert panel.result_list.count() == 3
    assert panel.selected_items() == []
    assert panel.btn_select_all.text() == "全选"

    panel.toggle_select_all()
    assert len(panel.selected_items()) == 3
    assert panel.btn_select_all.text() == "取消全选"

    panel.toggle_select_all()
    assert panel.selected_items() == []
    assert panel.btn_select_all.text() == "全选"

def test_dressup_panel_empty_results_are_warned_not_errors():
    app = QApplication.instance() or QApplication([])
    panel = DressupPanel()
    messages = []
    slot = lambda category, text: messages.append((category, text))
    app_signals.log_message.connect(slot)
    try:
        panel._on_results([])
    finally:
        app_signals.log_message.disconnect(slot)

    assert panel.count_label.text() == "未找到结果"
    assert messages == [(LogCategory.WARN, "未找到相关装扮或表情包")]


def test_download_panel_source_inputs_are_fixed_single_line_tabs():
    app = QApplication.instance() or QApplication([])
    panel = DownloadPanel(None, {"save_dir": ""})
    for input_edit in panel._inputs:
        assert input_edit.minimumHeight() == 34
        assert input_edit.maximumHeight() == 34
        assert input_edit.parent() is not panel.tabs

def test_download_panel_hides_empty_source_tab_area():
    app = QApplication.instance() or QApplication([])
    panel = DownloadPanel(None, {"save_dir": ""})
    panel.resize(900, 900)
    panel.show()
    app.processEvents()

    # 普通来源页签只有单行输入框，不应占用装扮结果列表所需的整块高度。
    assert panel.tabs.height() <= 80
    assert panel.input_bv.geometry().height() == 34

    # 切换到装扮页后，结果列表仍可使用可扩展空间。
    panel.tabs.setCurrentIndex(4)
    app.processEvents()
    assert panel.tabs.height() > 80
