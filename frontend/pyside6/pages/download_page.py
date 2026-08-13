"""下载页：左侧输入面板 + 右侧（登录状态卡片 + 彩色里程碑日志）。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QVBoxLayout, QWidget

from frontend.pyside6.widgets.download_panel import DownloadPanel
from frontend.pyside6.widgets.login_card import LoginCard
from frontend.pyside6.widgets.log_widget import LogWidget


class DownloadPage(QWidget):
    def __init__(self, settings, manager, parent=None):
        super().__init__(parent)
        self.manager = manager

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        self.panel = DownloadPanel(manager, settings)

        right = QWidget()
        right.setObjectName("PageRight")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(6)
        self.login_card = LoginCard()
        self.log_widget = LogWidget(settings)
        rv.addWidget(self.login_card)
        rv.addWidget(self.log_widget, 1)

        splitter.addWidget(self.panel)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([430, 620])

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(splitter)

        # manager 信号 → 面板的任务进度区
        manager.task_started.connect(self.panel.on_task_started)
        manager.task_progress.connect(self.panel.on_task_progress)
        manager.task_phase.connect(self.panel.on_task_phase)
        manager.task_finished.connect(self.panel.on_task_finished)
