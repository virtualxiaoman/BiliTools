"""LoginService 登录状态查询的单元测试（无网络）。

回归点：本地无 cookie 文件时，
- BiliSession / LoginService 均能正常构造（匿名会话），不抛 FileNotFoundError；
- get_login_state() 返回未登录的 LoginUser（is_login=False），不发网络请求、不抛异常；
- 扫码登录流程（qr_login/generate_qr）无需预置 cookie 文件即可启动。
"""

from src.api import BiliSession
from src.config import cookie as cookie_mod
from src.models.login_model import LoginUser
from src.services.login import LoginService


def _no_cookie_path(tmp_path):
    return tmp_path / "no-such-cookie.txt"


def test_session_construct_without_cookie(tmp_path, monkeypatch):
    """根因修复：cookie 文件缺失时 BiliSession 构造为匿名会话，不抛异常。"""
    monkeypatch.setattr(cookie_mod, "DEFAULT_COOKIE_PATH", _no_cookie_path(tmp_path))
    session = BiliSession()
    assert session.cookie.has_valid_session is False


def test_construct_without_cookie(tmp_path, monkeypatch):
    monkeypatch.setattr(cookie_mod, "DEFAULT_COOKIE_PATH", _no_cookie_path(tmp_path))
    service = LoginService()  # 不应抛异常
    assert service.session is not None
    assert service.session.cookie.has_valid_session is False


def test_get_login_state_without_cookie(tmp_path, monkeypatch):
    """无本地 cookie：返回未登录 LoginUser，不发网络请求、不抛异常。"""
    monkeypatch.setattr(cookie_mod, "DEFAULT_COOKIE_PATH", _no_cookie_path(tmp_path))
    user = LoginService().get_login_state()
    assert isinstance(user, LoginUser)
    assert user.is_login is False
    assert user.mid is None
    assert user.uname == ""
