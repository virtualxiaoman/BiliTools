"""账号切换弹窗：列出所有账号（昵称 + mid），单击切换，右键删除/设为默认。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QLabel, QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QPushButton, QVBoxLayout,
)

from src.services.account import AccountManager

from frontend.pyside6.workers.login_worker import recheck_login


class AccountSwitchDialog(QDialog):
    """下载页「切换」按钮弹出的账号选择框。

    单击账号立即切换；右键弹出菜单：设为默认 / 删除账号。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("切换账号")
        self.setMinimumWidth(340)
        self._manager = AccountManager()
        self._build()
        self._reload()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        hint = QLabel("点击账号切换；右键账号可设为默认或删除")
        hint.setObjectName("Dim")
        lay.addWidget(hint)

        self.list = QListWidget()
        self.list.itemClicked.connect(self._on_switch)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        lay.addWidget(self.list, 1)

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        lay.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _reload(self):
        self._manager.reload()
        self.list.clear()
        current = self._manager.get_current()
        for acc in self._manager.list_accounts():
            name = acc.user_name or f"账号{acc.mid}"
            text = f"{name}  （mid={acc.mid}）"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, acc.mid)
            if current is not None and acc.mid == current.mid:
                item.setText(f"★ {text}")
            self.list.addItem(item)

    # ---- 事件 ----

    def _on_switch(self, item):
        mid = item.data(Qt.ItemDataRole.UserRole)
        self._manager.switch(mid)
        recheck_login()
        self.accept()

    def _on_context_menu(self, pos):
        item = self.list.itemAt(pos)
        if item is None:
            return
        mid = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction("设为默认", lambda: self._set_default(mid))
        menu.addAction("删除账号", lambda: self._delete(mid))
        menu.exec(self.list.mapToGlobal(pos))

    def _set_default(self, mid):
        self._manager.set_default(mid)
        recheck_login()
        self._reload()

    def _delete(self, mid):
        acc = self._manager.get(mid)
        name = acc.user_name if acc and acc.user_name else f"账号{mid}"
        ans = QMessageBox.question(
            self, "删除账号",
            f"确定删除账号「{name}」（mid={mid}）及其 cookie 文件吗？",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._manager.remove(mid)  # 删除当前账号时自动切到剩余第一个
        recheck_login()
        self._reload()
