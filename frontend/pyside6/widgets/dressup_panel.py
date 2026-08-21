"""装扮页签：关键词搜索 + 多选下载。

一次搜索同时请求表情包、收藏集和主题装扮，结果按
``表情包-名称`` / ``收藏集-名称`` / ``装扮-名称`` 展示，
勾选框位于名称左侧，并提供“全选”按钮。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from frontend.pyside6.signals import LogCategory, app_signals
from frontend.pyside6.workers.search_worker import search_dressup


class DressupPanel(QWidget):
    """装扮页签主体：搜索输入 + 搜索结果多选列表。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        search_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("输入关键词，如 洛天依 / 初音未来")
        self.input.setClearButtonEnabled(True)
        self.btn_search = QPushButton("搜索")
        search_row.addWidget(self.input, 1)
        search_row.addWidget(self.btn_search)
        lay.addLayout(search_row)

        toolbar = QHBoxLayout()
        self.count_label = QLabel("搜索结果：0")
        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setEnabled(False)
        toolbar.addWidget(self.count_label)
        toolbar.addStretch(1)
        toolbar.addWidget(self.btn_select_all)
        lay.addLayout(toolbar)

        self.result_list = QListWidget()
        self.result_list.setWordWrap(True)
        self.result_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.result_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        lay.addWidget(self.result_list, 1)

        self.input.returnPressed.connect(self.search)
        self.btn_search.clicked.connect(self.search)
        self.btn_select_all.clicked.connect(self.toggle_select_all)
        self.result_list.itemChanged.connect(self._on_item_changed)

    # ---- 对外接口 ----

    def selected_items(self) -> list[dict]:
        """返回当前勾选的搜索结果（dict 列表，供下载 spec 使用）。"""
        items = []
        for i in range(self.result_list.count()):
            item = self.result_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                data = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict):
                    items.append(data)
        return items

    # ---- 搜索 ----

    def search(self):
        keyword = self.input.text().strip()
        if not keyword:
            app_signals.log_message.emit(LogCategory.WARN, "请输入装扮/表情包关键词")
            return

        self._clear_results()
        self.count_label.setText("搜索中…")
        self.btn_search.setEnabled(False)
        self.btn_select_all.setEnabled(False)
        self._worker = search_dressup(keyword, self._on_results, self._on_error)

    def _clear_results(self):
        self.result_list.blockSignals(True)
        self.result_list.clear()
        self.result_list.blockSignals(False)

    def _on_results(self, items: list):
        self.btn_search.setEnabled(True)
        self.result_list.blockSignals(True)
        self.result_list.clear()
        for data in items:
            if not isinstance(data, dict):
                continue
            display = str(data.get("display_name") or data.get("name") or "")
            if not display:
                continue
            item = QListWidgetItem(display)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, data)
            item.setToolTip(display)
            self.result_list.addItem(item)
        self.result_list.blockSignals(False)
        self._update_selection_state()

    def _on_error(self, text: str):
        self.btn_search.setEnabled(True)
        self.count_label.setText("搜索失败")
        self._update_selection_state()
        app_signals.log_message.emit(LogCategory.ERROR, f"装扮搜索失败：{text}")

    # ---- 全选 / 计数 ----

    def toggle_select_all(self):
        count = self.result_list.count()
        if count == 0:
            return
        all_checked = all(
            self.result_list.item(i).checkState() == Qt.CheckState.Checked
            for i in range(count)
        )
        state = Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked
        for i in range(count):
            self.result_list.item(i).setCheckState(state)

    def _on_item_changed(self, _item):
        self._update_selection_state()

    def _update_selection_state(self):
        count = self.result_list.count()
        selected = len(self.selected_items())
        self.count_label.setText(f"已选 {selected} / 共 {count}")
        self.btn_select_all.setEnabled(count > 0)
        self.btn_select_all.setText(
            "取消全选" if count and selected == count else "全选"
        )
