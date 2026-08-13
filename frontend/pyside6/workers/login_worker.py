"""登录相关线程：状态查询 + 扫码登录轮询。"""
import logging
import time

from PySide6.QtCore import QThread, Signal

from src.api.errors import BiliAuthError
from src.config.cookie import BiliCookies
from src.services.login import LoginService

from frontend.pyside6.signals import app_signals
from frontend.pyside6.utils import ensure_cookie_file

logger = logging.getLogger(__name__)

_QR_TEXT = {
    86101: "等待扫码…（请用哔哩哔哩 App 扫描）",
    86090: "扫码成功，请在手机上确认登录",
    86038: "二维码已失效，请重新生成",
    0: "登录成功",
}

_keepalive = []  # 防止后台 worker 被 GC


def _qr_text(code: int) -> str:
    return _QR_TEXT.get(code, f"未知状态（{code}）")


class LoginStateWorker(QThread):
    """查询一次登录状态。"""

    result = Signal(object)  # LoginUser | None

    def run(self):
        try:
            ensure_cookie_file()
            user = LoginService().get_login_state()
            self.result.emit(user)
        except BiliAuthError:
            # 未登录/登录失效：正常状态，不当作错误
            self.result.emit(None)
        except Exception as e:
            logger.warning("登录状态检查失败：%s", e)
            self.result.emit(None)


def query_login_async(callback) -> None:
    """后台查一次登录状态，结果交给 callback(LoginUser | None)。"""
    w = LoginStateWorker()
    w.result.connect(callback)
    w.finished.connect(lambda: _drop(w))
    _keepalive.append(w)
    w.start()


def start_login_check() -> None:
    """应用启动时后台检查一次登录状态。"""
    query_login_async(lambda u: app_signals.login_changed.emit(u))


def recheck_login() -> None:
    """下载彻底失败等场景下重新检查登录状态。"""
    start_login_check()


def shutdown_all() -> None:
    """应用退出前停止所有登录/二维码线程并等待（协作式，避免进程退出时崩溃）。"""
    for w in list(_keepalive):
        try:
            if w.isRunning():
                w.stop()
                w.wait(2000)
        except Exception:
            pass
        _drop(w)


def _drop(w):
    if w in _keepalive:
        _keepalive.remove(w)


class QrLoginWorker(QThread):
    """扫码登录：生成二维码 → 轮询状态 → 保存 cookie。"""

    qr_ready = Signal()          # 二维码图片已生成（读取 DEFAULT_QR_IMAGE_PATH）
    status = Signal(int, str)    # (状态码, 文案)
    done = Signal(bool, str)     # (是否成功, 信息)

    def __init__(self, timeout: float = 120.0, interval: float = 1.0, parent=None):
        super().__init__(parent)
        self.timeout = timeout
        self.interval = interval
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        self._stop = False
        try:
            ensure_cookie_file()
            service = LoginService()
            url, qrcode_key = service.generate_qr()
            self.qr_ready.emit()
            start = time.monotonic()
            while not self._stop:
                code, set_cookie = service.poll_full(qrcode_key)
                self.status.emit(code, _qr_text(code))
                if code == 0:
                    if set_cookie:
                        service.save_cookie(set_cookie)
                    BiliCookies.refresh()
                    # 新建 service：本 worker 的 service 构造于登录前，用的是旧(空)cookie，
                    # 直接 get_login_state 仍会 未登录。
                    user = LoginService().get_login_state()
                    app_signals.login_changed.emit(user)
                    self.done.emit(True, f"登录成功：{user.uname}")
                    return
                if code == 86038:
                    self.done.emit(False, "二维码已失效，请重新生成")
                    return
                if time.monotonic() - start > self.timeout:
                    self.done.emit(False, "扫码超时，请重新生成")
                    return
                time.sleep(self.interval)
            self.done.emit(False, "已取消")
        except Exception as e:
            logger.exception("扫码登录失败")
            self.done.emit(False, str(e))
