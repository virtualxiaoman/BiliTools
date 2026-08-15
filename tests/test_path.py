"""src.config.path 的 cookie 路径 getter/override 单元测试。"""

import pytest

from src.config import path as path_mod


@pytest.fixture(autouse=True)
def _reset_overrides():
    """每个用例复位两个 override，避免污染。"""
    path_mod.set_cookie_dir(None)
    path_mod.set_cookie_path(None)
    yield
    path_mod.set_cookie_dir(None)
    path_mod.set_cookie_path(None)


def test_defaults():
    assert path_mod.get_cookie_dir() == path_mod.COOKIE_ROOT
    assert path_mod.get_cookie_path() == path_mod.COOKIE_ROOT / "qr_login.txt"
    assert path_mod.get_qr_image_path() == path_mod.COOKIE_ROOT / "qr_login.png"


def test_set_cookie_dir(tmp_path):
    path_mod.set_cookie_dir(tmp_path)
    assert path_mod.get_cookie_dir() == tmp_path.resolve()
    assert path_mod.get_cookie_path() == tmp_path.resolve() / "qr_login.txt"
    assert path_mod.get_qr_image_path() == tmp_path.resolve() / "qr_login.png"


def test_set_cookie_dir_none_resets():
    path_mod.set_cookie_dir(r"C:\somewhere")
    path_mod.set_cookie_dir(None)
    assert path_mod.get_cookie_dir() == path_mod.COOKIE_ROOT


def test_set_cookie_dir_empty_str_resets():
    path_mod.set_cookie_dir(r"C:\somewhere")
    path_mod.set_cookie_dir("   ")
    assert path_mod.get_cookie_dir() == path_mod.COOKIE_ROOT


def test_set_cookie_path(tmp_path):
    target = tmp_path / "sub" / "cookie.txt"
    path_mod.set_cookie_path(target)
    assert path_mod.get_cookie_path() == target.resolve()
    # 目录 override 不影响文件级 override（当前账号优先）
    path_mod.set_cookie_dir(tmp_path / "dir")
    assert path_mod.get_cookie_path() == target.resolve()


def test_set_cookie_path_none_resets():
    path_mod.set_cookie_path(r"C:\x\y.txt")
    path_mod.set_cookie_path(None)
    assert path_mod.get_cookie_path() == path_mod.COOKIE_ROOT / "qr_login.txt"


def test_expanduser(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    path_mod.set_cookie_dir("~/mycookie")
    assert path_mod.get_cookie_dir() == (tmp_path / "mycookie").resolve()
