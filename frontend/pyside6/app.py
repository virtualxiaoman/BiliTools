"""应用装配：QApplication + 全局异常钩子 + 日志 + 主题 + 主窗口 + 启动登录检查。"""
import sys

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from src.config.path import ASSETS_DIR

from .logs import install_exception_hooks, install_logging
from .main_window import MainWindow
from .settings import Settings
from .signals import app_signals
from .theme import ThemeManager
from .utils import ensure_cookie_file
from .workers.login_worker import start_login_check


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("BiliTools")
    app.setOrganizationName("BiliTools")

    # 默认字体：明确指定点阵字号，避免 Qt 对 QSS 像素字号解析时报
    # "QFont::setPointSize: Point size <= 0 (-1)" 的警告；同时改善中文渲染。
    app.setFont(QFont("Microsoft YaHei UI", 9))

    icon_path = ASSETS_DIR / "imgs" / "ico" / "arona.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # 永不闪退：异常钩子必须最先装
    install_exception_hooks(app_signals)
    install_logging(app_signals)

    settings = Settings()
    theme_mgr = ThemeManager(settings)
    theme_mgr.apply(app)

    ensure_cookie_file()  # 全新安装：保证 cookie 文件存在，服务可构造

    window = MainWindow(settings, theme_mgr)
    window.show()

    # 启动时后台检查登录状态（约束 #8）
    start_login_check()

    return app.exec()
