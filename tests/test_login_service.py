"""LoginService 登录状态查询的单元测试（无网络）。

回归点：本地无 cookie 文件时，
- 构造 LoginService 不应抛 FileNotFoundError；
- get_login_state() 应返回未登录的 LoginUser（is_login=False），而不是抛异常；
- 登录流程（generate_qr）仍需 cookie 文件，缺失时保持抛 FileNotFoundError 原语义。
"""

import pytest

from src.config import cookie as cookie_mod
from src.models.login_model import LoginUser
from src.services.login import LoginService


def _no_cookie_path(tmp_path):
    return tmp_path / "no-such-cookie.txt"


def test_construct_without_cookie(tmp_path, monkeypatch):
    monkeypatch.setattr(cookie_mod, "DEFAULT_COOKIE_PATH", _no_cookie_path(tmp_path))
    service = LoginService()  # 不应抛异常
    assert service.session is None


def test_get_login_state_without_cookie(tmp_path, monkeypatch):
    """无本地 cookie：返回未登录 LoginUser，不发起网络请求、不抛异常。"""
    monkeypatch.setattr(cookie_mod, "DEFAULT_COOKIE_PATH", _no_cookie_path(tmp_path))
    user = LoginService().get_login_state()
    assert isinstance(user, LoginUser)
    assert user.is_login is False
    assert user.mid is None
    assert user.uname == ""


def test_generate_qr_without_cookie_still_raises(tmp_path, monkeypatch):
    """登录流程仍需要 cookie 文件：缺失时 generate_qr 保持抛 FileNotFoundError。"""
    monkeypatch.setattr(cookie_mod, "DEFAULT_COOKIE_PATH", _no_cookie_path(tmp_path))
    service = LoginService()
    with pytest.raises(FileNotFoundError):
        service.generate_qr()
