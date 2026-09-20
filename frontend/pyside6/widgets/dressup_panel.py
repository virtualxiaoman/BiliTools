"""装扮页签：关键词搜索 + 多选下载。

一次搜索同时请求表情包、收藏集和主题装扮，结果按
``表情包-名称`` / ``收藏集-名称`` / ``装扮-名称`` 展示，
勾选框位于名称左侧，并提供“全选”按钮。
"""

from PySide6.QtCore import Qt
from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from frontend.pyside6.signals import LogCategory, app_signals
from frontend.pyside6.workers.search_worker import import_dressup_by_ids, search_dressup
from src.services.dressup import DressupService


class DressupPanel(QWidget):
    """装扮页签主体：搜索输入 + 搜索结果多选列表。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._direct_worker = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        search_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("输入关键词，如 洛天依 / 初音未来")
        self.input.setClearButtonEnabled(True)
        self.input.setFixedHeight(34)
        self.btn_search = QPushButton("搜索")
        search_row.addWidget(self.input, 1)
        search_row.addWidget(self.btn_search)
        lay.addLayout(search_row)

        direct_link_row = QHBoxLayout()
        self.direct_link_input = QLineEdit()
        self.direct_link_input.setPlaceholderText("粘贴收藏集/主题装扮详情链接，可自动解析 ID")
        self.direct_link_input.setClearButtonEnabled(True)
        self.btn_parse_direct_link = QPushButton("解析链接")
        direct_link_row.addWidget(self.direct_link_input, 1)
        direct_link_row.addWidget(self.btn_parse_direct_link)
        lay.addLayout(direct_link_row)

        direct_id_row = QHBoxLayout()
        validator = QRegularExpressionValidator(QRegularExpression(r"[1-9]\d*"), self)
        self.act_id_input = QLineEdit()
        self.act_id_input.setPlaceholderText("活动 ID")
        self.act_id_input.setValidator(validator)
        self.lottery_id_input = QLineEdit()
        self.lottery_id_input.setPlaceholderText("卡池 ID")
        self.lottery_id_input.setValidator(validator)
        self.item_id_input = QLineEdit()
        self.item_id_input.setPlaceholderText("主题装扮 item ID")
        self.item_id_input.setValidator(validator)
        self.btn_import_by_id = QPushButton("按 ID 导入")
        direct_id_row.addWidget(self.act_id_input)
        direct_id_row.addWidget(self.lottery_id_input)
        direct_id_row.addWidget(self.item_id_input)
        direct_id_row.addWidget(self.btn_import_by_id)
        lay.addLayout(direct_id_row)

        self.direct_hint = QLabel("支持收藏集 act_id + lottery_id，或主题装扮 item_id")
        self.direct_hint.setStyleSheet("color: #808080;")
        lay.addWidget(self.direct_hint)

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
        self.direct_link_input.textChanged.connect(self._auto_parse_direct_link)
        self.direct_link_input.returnPressed.connect(self.parse_direct_link)
        self.btn_parse_direct_link.clicked.connect(self.parse_direct_link)
        self.btn_import_by_id.clicked.connect(self.import_by_id)
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

    # ---- 按 ID 导入 ----

    def _auto_parse_direct_link(self, value: str) -> None:
        """链接文本完整且可识别时立即填入相应 ID；输入中不输出错误日志。"""
        if not value.strip():
            self.direct_hint.setText("支持收藏集 act_id + lottery_id，或主题装扮 item_id")
            return
        try:
            reference = DressupService.parse_direct_url(value)
        except ValueError:
            return
        self._fill_direct_ids(reference)

    def parse_direct_link(self) -> bool:
        """显式解析链接；失败时只显示通用错误，不在界面回显 URL。"""
        try:
            reference = DressupService.parse_direct_url(self.direct_link_input.text())
        except ValueError as exc:
            self.direct_hint.setText("链接无法解析")
            app_signals.log_message.emit(LogCategory.WARN, f"按 ID 导入：{exc}")
            return False
        self._fill_direct_ids(reference)
        return True

    def _fill_direct_ids(self, reference: dict) -> None:
        if reference.get("kind") == "collection":
            self.act_id_input.setText(str(reference["act_id"]))
            self.lottery_id_input.setText(str(reference["lottery_id"]))
            self.item_id_input.clear()
            self.direct_hint.setText("已解析收藏集活动 ID 和卡池 ID，可点击“按 ID 导入”")
        else:
            self.item_id_input.setText(str(reference["item_id"]))
            self.act_id_input.clear()
            self.lottery_id_input.clear()
            self.direct_hint.setText("已解析主题装扮 item ID，可点击“按 ID 导入”")

    def import_by_id(self) -> None:
        """后台请求详情确认名称，再将导入项追加到当前可选下载列表。"""
        act_id = self.act_id_input.text().strip() or None
        lottery_id = self.lottery_id_input.text().strip() or None
        item_id = self.item_id_input.text().strip() or None
        if (act_id or lottery_id) and item_id:
            app_signals.log_message.emit(
                LogCategory.WARN, "请填写收藏集活动/卡池 ID，或主题装扮 item ID，不能同时填写",
            )
            return
        if not (act_id or lottery_id or item_id):
            app_signals.log_message.emit(LogCategory.WARN, "请先粘贴链接，或填写需要导入的 ID")
            return

        self.btn_import_by_id.setEnabled(False)
        self.direct_hint.setText("正在读取详情…")
        self._direct_worker = import_dressup_by_ids(
            act_id=act_id, lottery_id=lottery_id, item_id=item_id,
            on_result=self._on_direct_imported, on_error=self._on_direct_import_error,
        )

    def _on_direct_imported(self, data: dict) -> None:
        self.btn_import_by_id.setEnabled(True)
        if not isinstance(data, dict):
            self._on_direct_import_error("详情解析结果异常")
            return
        if self._contains_item(data):
            self.direct_hint.setText("该项目已在列表中")
            app_signals.log_message.emit(LogCategory.WARN, "该按 ID 导入的装扮已在列表中")
            return
        self._append_result(data, checked=True)
        self.direct_link_input.clear()
        self.direct_hint.setText("已导入，可在列表中勾选下载")
        app_signals.log_message.emit(
            LogCategory.NORMAL, f"已按 ID 导入：{data.get('display_name') or data.get('name') or '装扮'}",
        )

    def _on_direct_import_error(self, text: str) -> None:
        self.btn_import_by_id.setEnabled(True)
        self.direct_hint.setText("导入失败")
        app_signals.log_message.emit(LogCategory.ERROR, f"按 ID 导入失败：{text}")

    def _contains_item(self, data: dict) -> bool:
        kind = str(data.get("kind") or "")
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        for index in range(self.result_list.count()):
            existing = self.result_list.item(index).data(Qt.ItemDataRole.UserRole)
            if not isinstance(existing, dict) or existing.get("kind") != kind:
                continue
            existing_payload = existing.get("payload")
            if not isinstance(existing_payload, dict):
                continue
            if kind == "collection":
                properties = payload.get("properties")
                existing_properties = existing_payload.get("properties")
                if isinstance(properties, dict) and isinstance(existing_properties, dict) and (
                    properties.get("dlc_act_id"), properties.get("dlc_lottery_id")
                ) == (existing_properties.get("dlc_act_id"), existing_properties.get("dlc_lottery_id")):
                    return True
            elif kind == "suit" and payload.get("item_id") == existing_payload.get("item_id"):
                return True
        return False

    def _append_result(self, data: dict, *, checked: bool = False) -> None:
        display = str(data.get("display_name") or data.get("name") or "")
        if not display:
            return
        item = QListWidgetItem(display)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        item.setData(Qt.ItemDataRole.UserRole, data)
        item.setToolTip(display)
        self.result_list.addItem(item)
        self._update_selection_state()

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
            if isinstance(data, dict):
                self._append_result(data)
        self.result_list.blockSignals(False)
        self._update_selection_state()
        if self.result_list.count() == 0:
            # 搜索接口正常返回但没有可展示条目：这是空结果，不是异常。
            self.count_label.setText("未找到结果")
            app_signals.log_message.emit(LogCategory.WARN, "未找到相关装扮或表情包")

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
