"""应用装配：QApplication + 全局异常钩子 + 日志 + 主题 + 主窗口 + 启动登录检查。"""
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from src.config.path import ASSETS_DIR, set_cookie_dir
from src.services.account import AccountManager

from frontend.pyside6.fonts import app_font, load_fonts, set_zoom
from frontend.pyside6.logs import install_exception_hooks, install_logging
from frontend.pyside6.main_window import MainWindow
from frontend.pyside6.settings import Settings
from frontend.pyside6.signals import app_signals
from frontend.pyside6.theme import ThemeManager
from frontend.pyside6.utils import ensure_cookie_file
from frontend.pyside6.workers.login_worker import start_login_check


def main() -> int:
    # Windows：为进程设置显式 AppUserModelID，任务栏才能正确关联应用图标
    # （否则以 python 启动时任务栏不显示图标或显示 python 的图标）。
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("BiliTools")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("BiliTools")
    app.setOrganizationName("BiliTools")

    # 界面字体：优先方正兰亭圆（常规），缺失时回退系统字体。
    # 下载日志内容单独使用系统字体（log_widget），基准字号不随界面调大。
    load_fonts()

    settings = Settings()
    # 应用全局 cookie 目录设置与当前账号（必须先于 ensure_cookie_file，避免在默认目录建空文件）
    set_cookie_dir(settings.get("cookie_dir"))
    AccountManager().apply_startup()
    # 先读保存的缩放系数，再设默认字体与 QSS（theme_mgr.apply 会带上缩放）
    set_zoom(settings.get("zoom", 1.0))
    app.setFont(app_font())

    icon_path = ASSETS_DIR / "imgs" / "ico" / "arona.ico"
    window_icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
    if not window_icon.isNull():
        app.setWindowIcon(window_icon)

    # 永不闪退：异常钩子必须最先装
    install_exception_hooks(app_signals)
    install_logging(app_signals)

    theme_mgr = ThemeManager(settings)
    theme_mgr.apply(app)

    ensure_cookie_file()  # 全新安装：保证 cookie 文件存在，服务可构造

    window = MainWindow(settings, theme_mgr)
    # 显式给顶层窗口设图标：仅 setApplicationIcon 在 Windows 上不一定传导到
    # 无边框窗口的任务栏入口。
    if not window_icon.isNull():
        window.setWindowIcon(window_icon)
    window.show()

    # 启动时后台检查登录状态（约束 #8）
    start_login_check()

    return app.exec()
