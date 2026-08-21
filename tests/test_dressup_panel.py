"""装扮页签 UI 行为测试（离屏 Qt）：勾选、全选、选中列表。"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from frontend.pyside6.widgets.dressup_panel import DressupPanel


def _items():
    return [
        {"kind": "emoji", "name": "表情包A", "display_name": "表情包-表情包A", "payload": {"id": 1}},
        {"kind": "collection", "name": "收藏集A", "display_name": "收藏集-收藏集A", "payload": {"name": "收藏集A"}},
        {"kind": "suit", "name": "装扮B", "display_name": "装扮-装扮B", "payload": {"item_id": 2}},
    ]


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
