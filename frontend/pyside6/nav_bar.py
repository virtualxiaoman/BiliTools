"""导航栏：功能切换（下载 / 登录 / 设置）。运行中任务数已移到标题栏居中显示。"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QTabBar, QWidget


class NavBar(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NavBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(44)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 12, 0)
        lay.setSpacing(0)

        self.tabbar = QTabBar()
        self.tabbar.setExpanding(True)
        self.tabbar.setDrawBase(False)
        for name in ("下载", "登录", "设置"):
            self.tabbar.addTab(name)
        self.tabbar.currentChanged.connect(self.currentChanged)

        lay.addWidget(self.tabbar)

    def set_current(self, index):
        self.tabbar.setCurrentIndex(index)
