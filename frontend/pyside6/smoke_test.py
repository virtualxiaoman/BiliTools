"""离屏冒烟测试：验证前端模块可构建、日志渲染、导航、主题、去重。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "")
ROOT = r"G:\Projects\py\BiliTools"
sys.path.insert(0, ROOT)

RESULT = os.path.join(ROOT, "output", "logs", "smoke_result.txt")
os.makedirs(os.path.dirname(RESULT), exist_ok=True)
out = open(RESULT, "w", encoding="utf-8")


def log(*a):
    out.write(" ".join(str(x) for x in a) + "\n")
    out.flush()


try:
    from PySide6.QtWidgets import QApplication
    from src.config.path import set_cookie_dir
    from src.services.account import AccountManager
    from frontend.pyside6.logs import install_exception_hooks, install_logging
    from frontend.pyside6.signals import app_signals, LogCategory
    from frontend.pyside6.settings import Settings
    from frontend.pyside6.theme import ThemeManager
    from frontend.pyside6.main_window import MainWindow
    from frontend.pyside6.utils import ensure_cookie_file, normalize_bvid, normalize_fav, normalize_season, normalize_mid
    from frontend.pyside6.utils import has_valid_session
    from frontend.pyside6.workers.progress_adapter import ProgressAdapter
    from PySide6.QtCore import QObject, Signal

    app = QApplication(sys.argv)
    install_exception_hooks(app_signals)
    install_logging(app_signals)
    settings = Settings()
    set_cookie_dir(settings.get("cookie_dir"))  # 与真实装配一致
    AccountManager().apply_startup()
    tm = ThemeManager(settings)
    tm.apply(app)
    ensure_cookie_file()

    win = MainWindow(settings, tm)
    win.show()
    win.login_page._started = True  # 禁止登录页首次显示时自动拉起二维码轮询线程（避免真实网络副作用）
    log("MainWindow built OK")
    panel = win.download_page.panel
    log("download tabs:", [panel.tabs.tabText(i) for i in range(panel.tabs.count())])
    panel.tabs.setCurrentIndex(4)
    app.processEvents()
    log("dressup tab count:", panel.dressup_panel.result_list.count())

    # ---- 日志渲染 ----
    app_signals.log_message.emit(LogCategory.NORMAL, "普通信息测试")
    app_signals.log_message.emit(LogCategory.PROGRESS, "正在下载 第 3/24 个：test.mp4")
    app_signals.log_message.emit(LogCategory.WARN, "警告测试")
    app_signals.log_message.emit(LogCategory.ERROR, "报错测试")
    app_signals.log_message.emit(LogCategory.SUCCESS, "完成测试")
    app.processEvents()
    doc = win.download_page.log_widget.text.document()
    log("log blockCount:", doc.blockCount())

    # ---- 导航 ----
    app_signals.goto_page.emit("login")
    app.processEvents()
    log("page after goto login:", win.stack.currentIndex())
    win.nav_bar.set_current(2)
    app.processEvents()
    log("page after nav settings:", win.stack.currentIndex())

    # ---- 主题 ----
    tm.set_theme("dark")
    app.processEvents()
    log("theme:", tm.current(), "| settings.theme:", settings.get("theme"))

    # ---- 输入归一化 ----
    log("normalize_bvid(bv lowercase):", normalize_bvid("bv1ov42117yC"))
    log("normalize_bvid(av):", normalize_bvid("av1744064181"))
    log("normalize_fav(url):", normalize_fav("https://space.bilibili.com/506925078/favlist?fid=3953119978&ftype=create"))
    log("normalize_season(sid):", normalize_season("8683221"))
    log("normalize_season(url):", normalize_season("https://space.bilibili.com/506925078/channel/collectiondetail?sid=8683221"))
    log("normalize_mid(url):", normalize_mid("https://space.bilibili.com/249056021"))
    try:
        normalize_bvid("不是个视频")
        log("normalize_bvid bad: NO ERROR (BAD)")
    except ValueError:
        log("normalize_bvid bad: raised ValueError OK")

    # ---- 登录门禁（强制未登录，验证拦截 + 跳转登录页） ----
    log("has_valid_session(真实环境):", has_valid_session())
    import frontend.pyside6.workers.download_manager as dm
    dm.has_valid_session = lambda: False  # 强制未登录，避免真实起下载线程
    tid = win.manager.submit({"source": "bv", "input": "BV1ov42117yC", "scope": "all", "page": 1,
                              "media_type": "video_with_audio", "quality": 120,
                              "save_dir": "output", "desc": "smoke"})
    app.processEvents()
    log("submit when logged out returned:", tid, "(None = blocked OK)")
    log("current page after gate:", win.stack.currentIndex(), "(1=login OK)")
    dm.has_valid_session = lambda: True  # 恢复

    # ---- 去重 key ----
    key1 = win.manager._make_key({"source": "bv", "input": "BV1ov42117yC", "scope": "all", "page": 1,
                                  "media_type": "video_with_audio", "quality": 120, "save_dir": "output"})
    key2 = win.manager._make_key({"source": "bv", "input": "BV1ov42117yC", "scope": "all", "page": 1,
                                  "media_type": "video_with_audio", "quality": 120, "save_dir": "output"})
    key3 = win.manager._make_key({"source": "bv", "input": "BV1ov42117yC", "scope": "all", "page": 1,
                                  "media_type": "video_with_audio", "quality": 80, "save_dir": "output"})
    log("dedup same:", key1 == key2, "| dedup diff quality:", key1 != key3)

    # ---- ProgressAdapter（不联网） ----
    class FakeWorker(QObject):
        progress = Signal(int, int)
        def __init__(self):
            super().__init__()
            self.milestones = []
        def milestone(self, cat, text):
            self.milestones.append((int(cat), text))
        def phase(self, t):
            pass

    fw = FakeWorker()
    pa = ProgressAdapter(4, "测试", fw)
    pa.start(1, "a.mp4")
    pa.add(1024 * 1024 * 2, 1024 * 1024 * 4)
    pa.finish()
    app.processEvents()
    log("adapter milestones:", fw.milestones)

    # ---- SDK 增强可导入 ----
    from src.services.video import VideoService
    from src.services.login import LoginService
    import inspect
    sig_fav = inspect.signature(VideoService.download_fav)
    sig_up = inspect.signature(VideoService.download_up)
    sig_poll = inspect.signature(LoginService.poll_full)
    log("download_fav has progress:", "progress" in sig_fav.parameters)
    log("download_up has progress:", "progress" in sig_up.parameters)
    log("poll_full signature:", sig_poll)

    log("SMOKE OK")
    app.quit()
    sys.exit(0)
except Exception as e:
    import traceback
    log("SMOKE FAIL:", e)
    log(traceback.format_exc())

out.close()
