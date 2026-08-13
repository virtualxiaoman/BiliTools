"""主窗口：标题栏 + 导航栏 + 内容区（QStackedWidget）。无边框。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from .nav_bar import NavBar
from .pages.download_page import DownloadPage
from .pages.login_page import LoginPage
from .pages.settings_page import SettingsPage
from .signals import app_signals
from .title_bar import TitleBar
from .workers.download_manager import DownloadManager


class MainWindow(QWidget):
    PAGE_INDEX = {"download": 0, "login": 1, "settings": 2}

    def __init__(self, settings, theme_mgr, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.theme_mgr = theme_mgr
        self.manager = DownloadManager(self)
        self._build()

    def _build(self):
        self.setWindowTitle("BiliTools")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.resize(1100, 700)
        self.setMinimumSize(980, 640)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.title_bar = TitleBar(self)
        self.nav_bar = NavBar()

        self.stack = QStackedWidget()
        self.download_page = DownloadPage(self.settings, self.manager)
        self.login_page = LoginPage()
        self.settings_page = SettingsPage(self.settings, self.theme_mgr)
        self.stack.addWidget(self.download_page)   # 0
        self.stack.addWidget(self.login_page)      # 1
        self.stack.addWidget(self.settings_page)   # 2

        outer.addWidget(self.title_bar)
        outer.addWidget(self.nav_bar)
        outer.addWidget(self.stack, 1)

        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.maximize_requested.connect(self._toggle_maximize)
        self.title_bar.close_requested.connect(self.close)
        self.title_bar.theme_toggled.connect(self._toggle_theme)
        self.nav_bar.currentChanged.connect(self.stack.setCurrentIndex)
        self.manager.count_changed.connect(self.title_bar.set_task_count)

        app_signals.goto_page.connect(self._goto_page)

    # ---- 窗口动作 ----

    def _toggle_theme(self):
        nxt = "dark" if self.theme_mgr.current() == "light" else "light"
        self.theme_mgr.set_theme(nxt)

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _goto_page(self, name):
        idx = self.PAGE_INDEX.get(name)
        if idx is not None:
            self.nav_bar.set_current(idx)
            self.stack.setCurrentIndex(idx)

    def closeEvent(self, event):
        if self.manager.has_running():
            ans = QMessageBox.question(
                self, "退出 BiliTools", "有下载任务正在运行，确定要退出吗？"
            )
            if ans != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        # 停止后台线程，避免进程退出时 QThread 仍运行导致崩溃
        self.manager.shutdown()
        from .workers.login_worker import shutdown_all
        shutdown_all()
        super().closeEvent(event)
