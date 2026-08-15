"""AccountManager 多账号映射表的单元测试（无网络）。"""

import json

import pytest

from src.config import path as path_mod
from src.config.cookie import BiliCookies
from src.services.account import AccountManager


@pytest.fixture(autouse=True)
def _isolate_cookie():
    """每个用例复位全局 cookie override 并清缓存。"""
    path_mod.set_cookie_dir(None)
    path_mod.set_cookie_path(None)
    BiliCookies.clear_cache()
    yield
    path_mod.set_cookie_dir(None)
    path_mod.set_cookie_path(None)
    BiliCookies.clear_cache()


def _manager(tmp_path):
    return AccountManager(accounts_file=tmp_path / "accounts.json")


def test_upsert_and_list(tmp_path):
    m = _manager(tmp_path)
    m.upsert(123, "小明", tmp_path / "a.txt")
    m.upsert(456, "小红", tmp_path / "b.txt")
    assert len(m.list_accounts()) == 2
    assert m.get(123).user_name == "小明"
    assert m.get(999) is None


def test_upsert_same_mid_updates(tmp_path):
    m = _manager(tmp_path)
    m.upsert(123, "小明", tmp_path / "a.txt")
    m.upsert(123, "新昵称", tmp_path / "a2.txt")
    assert len(m.list_accounts()) == 1
    acc = m.get(123)
    assert acc.user_name == "新昵称"
    assert acc.cookie_path == tmp_path / "a2.txt"


def test_switch_applies_cookie_path_and_persists(tmp_path):
    m = _manager(tmp_path)
    m.upsert(123, "小明", tmp_path / "cookie123.txt")
    m.upsert(456, "小红", tmp_path / "cookie456.txt")
    m.switch(456)
    assert path_mod.get_cookie_path() == (tmp_path / "cookie456.txt").resolve()
    assert m.get_current().mid == 456
    m.switch(123)
    assert path_mod.get_cookie_path() == (tmp_path / "cookie123.txt").resolve()
    data = json.loads((tmp_path / "accounts.json").read_text(encoding="utf-8"))
    assert data["current_mid"] == 123


def test_switch_unknown_mid_clears_current(tmp_path):
    m = _manager(tmp_path)
    m.upsert(123, "小明", tmp_path / "cookie123.txt")
    m.switch(123)
    m.switch(999)  # 不存在的 mid → 无当前账号，回落默认
    assert m.get_current() is None
    assert path_mod.get_cookie_path() == path_mod.get_cookie_dir() / "qr_login.txt"


def test_remove_deletes_file_and_switches_next(tmp_path):
    m = _manager(tmp_path)
    f = tmp_path / "cookie123.txt"
    f.write_text("SESSDATA=x", encoding="utf-8")
    m.upsert(123, "小明", f)
    m.upsert(456, "小红", tmp_path / "cookie456.txt")
    m.switch(123)
    m.remove(123)
    assert not f.exists()
    assert m.get(123) is None
    assert m.get_current().mid == 456  # 自动切到剩余第一个
    assert path_mod.get_cookie_path() == (tmp_path / "cookie456.txt").resolve()


def test_relocate_moves_under_old_dir(tmp_path):
    m = _manager(tmp_path)
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_cookie = old_dir / "123" / "qr_login.txt"
    old_cookie.parent.mkdir(parents=True)
    old_cookie.write_text("SESSDATA=abc", encoding="utf-8")
    m.upsert(123, "小明", old_cookie)
    path_mod.set_cookie_dir(old_dir)
    m.relocate(old_dir, new_dir)
    assert not old_cookie.exists()
    assert (new_dir / "123" / "qr_login.txt").read_text(encoding="utf-8") == "SESSDATA=abc"
    assert m.get(123).cookie_path == new_dir / "123" / "qr_login.txt"
    data = json.loads((tmp_path / "accounts.json").read_text(encoding="utf-8"))
    assert data["accounts"][0]["cookie_path"] == str(new_dir / "123" / "qr_login.txt")


def test_relocate_keeps_custom_paths(tmp_path):
    m = _manager(tmp_path)
    custom = tmp_path / "custom" / "c.txt"
    custom.parent.mkdir(parents=True)
    custom.write_text("x", encoding="utf-8")
    m.upsert(123, "小明", custom)
    m.relocate(tmp_path / "old", tmp_path / "new")
    assert custom.exists()
    assert m.get(123).cookie_path == custom


def test_corrupted_table_falls_back(tmp_path):
    f = tmp_path / "accounts.json"
    f.write_text("{ not json", encoding="utf-8")
    m = AccountManager(accounts_file=f)
    assert m.list_accounts() == []
    assert m.get_current() is None


def test_apply_startup(tmp_path):
    m = _manager(tmp_path)
    m.upsert(123, "小明", tmp_path / "cookie123.txt")
    m.switch(123)
    path_mod.set_cookie_path(None)  # 模拟未应用状态
    BiliCookies.clear_cache()
    m2 = AccountManager(accounts_file=tmp_path / "accounts.json")
    m2.apply_startup()
    assert path_mod.get_cookie_path() == (tmp_path / "cookie123.txt").resolve()


def test_default_cookie_path_uses_configured_dir(tmp_path):
    m = _manager(tmp_path)
    path_mod.set_cookie_dir(tmp_path / "dir")
    assert m.default_cookie_path(42) == (tmp_path / "dir" / "42" / "qr_login.txt").resolve()


def test_handle_login_writes_and_switches(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    path_mod.set_cookie_dir(tmp_path / "dir")
    monkeypatch.setattr(AccountManager, "_resolve_uname", staticmethod(lambda: "小明"))
    set_cookie = "SESSDATA=abc; DedeUserID=42; bili_jct=xyz"
    account = m.handle_login(set_cookie)
    assert account is not None
    assert account.mid == 42
    assert account.user_name == "小明"
    cookie_file = tmp_path / "dir" / "42" / "qr_login.txt"
    assert cookie_file.exists()
    assert cookie_file.read_text(encoding="utf-8") == set_cookie
    assert m.get_current().mid == 42
    assert path_mod.get_cookie_path() == cookie_file.resolve()


def test_handle_login_fallback_mid_zero(tmp_path, monkeypatch):
    """set-cookie 无 DedeUserID 且在线解析失败时，用 mid=0 占位，避免叠账号。"""
    m = _manager(tmp_path)
    path_mod.set_cookie_dir(tmp_path / "dir")
    monkeypatch.setattr(AccountManager, "_resolve_mid_online", staticmethod(lambda _c: None))
    monkeypatch.setattr(AccountManager, "_resolve_uname", staticmethod(lambda: ""))
    account = m.handle_login("SESSDATA=abc")
    assert account is not None
    assert account.mid == 0
    assert m.get_current().mid == 0


def test_set_default_marks_and_switches(tmp_path):
    m = _manager(tmp_path)
    m.upsert(123, "小明", tmp_path / "cookie123.txt")
    m.upsert(456, "小红", tmp_path / "cookie456.txt")
    m.switch(456)
    m.set_default(123)
    assert m.default_mid == 123
    assert m.get_current().mid == 123  # 设为默认立即切换
    assert path_mod.get_cookie_path() == (tmp_path / "cookie123.txt").resolve()
    data = json.loads((tmp_path / "accounts.json").read_text(encoding="utf-8"))
    assert data["default_mid"] == 123


def test_apply_startup_prefers_default(tmp_path):
    m = _manager(tmp_path)
    m.upsert(123, "小明", tmp_path / "cookie123.txt")
    m.upsert(456, "小红", tmp_path / "cookie456.txt")
    m.switch(456)            # 会话内切到 456
    m.set_default(123)       # 默认账号为 123
    path_mod.set_cookie_path(None)
    BiliCookies.clear_cache()
    m2 = AccountManager(accounts_file=tmp_path / "accounts.json")
    m2.apply_startup()
    assert m2.get_current().mid == 123  # 启动默认优先于上次会话的 current
    assert path_mod.get_cookie_path() == (tmp_path / "cookie123.txt").resolve()
