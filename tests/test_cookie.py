"""Cookie 解析与缓存的单元测试。"""

from pathlib import Path

import pytest

from src.config.cookie import BiliCookies

RAW_COOKIE = "SESSDATA=abc123; bili_jct=csrf456; DedeUserID=506925078; sid=xyz; other=zzz"


def test_parse_fields():
    c = BiliCookies(cookie=RAW_COOKIE)
    assert c.SESSDATA == "abc123"
    assert c.bili_jct == "csrf456"
    assert c.has_valid_session


def test_parse_missing_field():
    c = BiliCookies(cookie="DedeUserID=1;")
    assert c.SESSDATA is None
    assert c.bili_jct is None
    assert not c.has_valid_session


def test_from_file(tmp_path):
    f = tmp_path / "cookie.txt"
    f.write_text(RAW_COOKIE, encoding="utf-8")
    c = BiliCookies.from_file(f)
    assert c.SESSDATA == "abc123"


def test_from_file_cache_same_instance(tmp_path):
    f = tmp_path / "cookie.txt"
    f.write_text(RAW_COOKIE, encoding="utf-8")
    c1 = BiliCookies.from_file(f)
    c2 = BiliCookies.from_file(f)
    assert c1 is c2  # 进程内缓存


def test_refresh_overrides_cache(tmp_path):
    f = tmp_path / "cookie.txt"
    f.write_text("SESSDATA=old;", encoding="utf-8")
    c1 = BiliCookies.from_file(f)
    assert c1.SESSDATA == "old"
    f.write_text("SESSDATA=new;", encoding="utf-8")
    c2 = BiliCookies.refresh(f)
    assert c2.SESSDATA == "new"
    assert c2 is not c1


def test_from_file_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        BiliCookies.from_file(tmp_path / "nope.txt")


def test_to_headers_contains_cookie():
    c = BiliCookies(cookie=RAW_COOKIE)
    headers = c.to_headers()
    assert headers["Cookie"] == RAW_COOKIE
    assert "User-Agent" in headers
    assert headers["Referer"] == "https://www.bilibili.com/"


def test_repr_hides_cookie():
    c = BiliCookies(cookie=RAW_COOKIE)
    assert RAW_COOKIE not in repr(c)
    assert "SESSDATA" in repr(c)
