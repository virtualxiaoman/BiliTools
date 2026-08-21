"""前端输入归一化单元测试（无网络，不触网）。

本地能解析的输入（BV/av/完整 URL 带 id）直接归一化；本地解析不出的短链抛
NeedsUrlResolution，交由下载线程 resolve_input 跟随跳转（跳转本身被 monkeypatch）。
"""
import pytest

from frontend.pyside6.utils import (
    NeedsUrlResolution, extract_page_from_url, normalize_bvid, normalize_fav,
    normalize_emote_ids, normalize_mid, normalize_season, resolve_input,
)


def test_normalize_bvid_av_in_url():
    """链接路径中的 av 号直接解析为 BV，不依赖网络 301 跳转。

    （该 av 号非真实视频，页面不会重定向到 BV，旧实现会解析失败。）
    """
    assert normalize_bvid(
        "https://www.bilibili.com/video/av114986911276172/"
        "?vd_source=1d4bb9016526d54e19438a12d0695200"
    ) == "BV1YVtqzjED2"
    assert normalize_bvid("https://www.bilibili.com/video/av170001") == "BV17x411w7KC"


def test_normalize_bvid_bare_av():
    """裸 av 号仍可直接转换（原 fullmatch 行为由 _AV_RE 的 ^ 分支覆盖）。"""
    assert normalize_bvid("av170001") == "BV17x411w7KC"
    assert normalize_bvid("AV170001") == "BV17x411w7KC"


def test_normalize_bvid_av_must_have_digits():
    """av 后必须跟数字；'av' 接非数字不匹配、不触网，直接报错。"""
    with pytest.raises(ValueError):
        normalize_bvid("avXYZ")


def test_local_urls_parse_without_network():
    """完整 URL 里带 id 的：本地正则直接解析，不发网络请求。"""
    assert normalize_fav(
        "https://space.bilibili.com/506925078/favlist?fid=3953119978&ftype=create") == 3953119978
    assert normalize_mid("https://space.bilibili.com/249056021/video") == 249056021


def test_short_link_raises_needs_resolution():
    """本地解析不出的短链抛 NeedsUrlResolution（不触网），由下载线程处理。"""
    with pytest.raises(NeedsUrlResolution):
        normalize_bvid("https://b23.tv/AbC123")
    with pytest.raises(NeedsUrlResolution):
        normalize_fav("https://b23.tv/AbC123")
    with pytest.raises(NeedsUrlResolution):
        normalize_mid("https://b23.tv/xYz789")
    with pytest.raises(NeedsUrlResolution):
        normalize_season("https://b23.tv/qWe456")


def test_title_plus_short_link_extracts_url():
    """「标题+短链」格式：NeedsUrlResolution 只携带提取出的干净 URL，标题不进请求。"""
    with pytest.raises(NeedsUrlResolution) as exc:
        normalize_bvid("【【洛天依kigurumi】天依和她的小洛包…-哔哩哔哩】 https://b23.tv/z781jBr")
    assert exc.value.url == "https://b23.tv/z781jBr"

    with pytest.raises(NeedsUrlResolution) as exc:
        normalize_fav("收藏夹分享 https://b23.tv/AbC123 嘿嘿")
    assert exc.value.url == "https://b23.tv/AbC123"

    with pytest.raises(NeedsUrlResolution) as exc:
        normalize_mid("UP主 https://b23.tv/xYz789")
    assert exc.value.url == "https://b23.tv/xYz789"

    with pytest.raises(NeedsUrlResolution) as exc:
        normalize_season("合集 https://b23.tv/qWe456")
    assert exc.value.url == "https://b23.tv/qWe456"


def test_title_plus_bv_url_parses_locally():
    """「标题+完整 BV 链接」：本地正则直接找到 BV，无需跳转。"""
    assert normalize_bvid(
        "【【洛天依kigurumi】天依和她的小洛包…】 "
        "https://www.bilibili.com/video/BV1pvgG6PEmB/"
        "?share_source=copy_web&vd_source=267c8f5c87819349e8a1e0fa6018b9e0"
    ) == "BV1pvgG6PEmB"


def test_title_plus_av_url_parses_locally():
    """「标题+av 链接」：本地 av2bv 直接转换。"""
    assert normalize_bvid("【标题】 https://www.bilibili.com/video/av170001?p=2") == "BV17x411w7KC"


def test_resolve_input_title_plus_short_link(monkeypatch):
    """标题+短链 → 下载线程先提取干净 URL、跟随跳转、解析出 BV。"""
    import frontend.pyside6.utils as u

    seen = []

    def fake_follow(url):
        seen.append(url)
        return "https://www.bilibili.com/video/BV1pvgG6PEmB/"

    monkeypatch.setattr(u, "follow_redirect", fake_follow)
    assert resolve_input("bv", "【标题】 https://b23.tv/z781jBr") == "BV1pvgG6PEmB"
    assert seen == ["https://b23.tv/z781jBr"]  # 传给跳转的是干净 URL，不含标题


def test_resolve_input_follows_short_link(monkeypatch):
    """resolve_input（下载线程）：跟随跳转后重新本地解析为规范值。"""
    import frontend.pyside6.utils as u

    monkeypatch.setattr(u, "follow_redirect",
                        lambda url: "https://www.bilibili.com/video/BV1ws411v7zE")
    assert resolve_input("bv", "https://b23.tv/AbC123") == "BV1ws411v7zE"

    monkeypatch.setattr(u, "follow_redirect",
                        lambda url: "https://space.bilibili.com/506925078/favlist?fid=42")
    assert resolve_input("fav", "https://b23.tv/AbC123") == 42
    assert resolve_input("up", "https://b23.tv/xYz789") == 506925078

    monkeypatch.setattr(
        u, "follow_redirect",
        lambda url: "https://space.bilibili.com/506925078/channel/collectiondetail?sid=1717000")
    assert resolve_input("season", "https://b23.tv/qWe456") == ("sid", 1717000, 506925078)


def test_resolve_input_redirect_failure(monkeypatch):
    """跟随跳转失败（网络异常）→ 转为 ValueError。"""
    import requests

    import frontend.pyside6.utils as u

    def boom(url):
        raise requests.RequestException("timeout")

    monkeypatch.setattr(u, "follow_redirect", boom)
    with pytest.raises(ValueError):
        resolve_input("bv", "https://b23.tv/AbC123")



def test_normalize_season_lists_url():
    """合集空间链接 /mid/lists/sid：按路径结构提取，不依赖 ?type=season。"""
    assert normalize_season("https://space.bilibili.com/506925078/lists/1717000?type=season") \
        == ("sid", 1717000, 506925078)
    assert normalize_season("https://space.bilibili.com/506925078/lists/1717000") \
        == ("sid", 1717000, 506925078)


def test_normalize_season_sid_param():
    assert normalize_season("https://space.bilibili.com/506925078/channel/collectiondetail?sid=1717000") \
        == ("sid", 1717000, 506925078)


def test_normalize_season_plain_sid():
    assert normalize_season("8683221") == ("sid", 8683221, 0)


def test_normalize_season_bvid():
    assert normalize_season("BV1Q43w6QETb") == ("bvid", "BV1Q43w6QETb", None)


def test_extract_page_from_url():
    assert extract_page_from_url(
        "https://www.bilibili.com/video/BV1ws411v7zE?spm_id_from=333&vd_source=x&p=2") == 2
    assert extract_page_from_url("https://www.bilibili.com/video/BV1ws411v7zE") is None
    assert extract_page_from_url("BV1ws411v7zE") is None

def test_normalize_emote_ids_accepts_comma_separated_ids_and_api_url():
    assert normalize_emote_ids("10239, 10238,10239") == (10239, 10238)
    assert normalize_emote_ids(
        "https://api.bilibili.com/x/emote/package?business=reply&ids=10239,10238"
    ) == (10239, 10238)


def test_normalize_emote_ids_rejects_invalid_values():
    with pytest.raises(ValueError):
        normalize_emote_ids("10239,not-an-id")
