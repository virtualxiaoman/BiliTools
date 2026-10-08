"""按 ID 导入装扮的回归测试。"""

import pytest

from src.services.dressup import DressupService
from src.urls.emote_urls import EmoteUrls
from src.urls.garb_urls import GarbUrls


class _Session:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.session = type("RequestsSession", (), {"headers": {}})()

    def get(self, url, params=None):
        self.calls.append((url, params))
        return self.responses[(url, tuple(sorted((params or {}).items())))]


def _key(url, **params):
    return url, tuple(sorted(params.items()))


def test_parse_direct_url_supports_collection_and_suit():
    assert DressupService.parse_direct_url(
        r"https://api.bilibili.com/x/vas/dlc_act/lottery_home_detail?act_id=108477\&lottery_id=108559"
    ) == {"kind": "collection", "act_id": 108477, "lottery_id": 108559}
    assert DressupService.parse_direct_url(
        "https://api.bilibili.com/x/garb/v2/mall/suit/detail?item_id=35789"
    ) == {"kind": "suit", "item_id": 35789}


def test_parse_direct_url_supports_emote_package_link():
    assert DressupService.parse_direct_url(
        "https://api.bilibili.com/x/emote/package?business=reply&ids=10239,10238"
    ) == {"kind": "emoji", "package_id": 10239}


def test_import_by_ids_fetches_detail_and_builds_compatible_items():
    session = _Session({
        _key(GarbUrls.COLLECTION_DETAIL, act_id=108477, lottery_id=108559): {"name": "历史收藏集"},
        _key(GarbUrls.SUIT_DETAIL, item_id=35789): {"name": "历史装扮"},
    })
    service = DressupService(session)

    collection = service.import_by_ids(act_id="108477", lottery_id="108559")
    suit = service.import_by_ids(item_id="35789")

    assert collection.name == "历史收藏集"
    assert collection.payload["properties"] == {"dlc_act_id": 108477, "dlc_lottery_id": 108559}
    assert collection.payload["direct_import"] is True
    assert suit.name == "历史装扮"
    assert suit.payload["item_id"] == 35789
    assert session.calls == [
        (GarbUrls.COLLECTION_DETAIL, {"act_id": 108477, "lottery_id": 108559}),
        (GarbUrls.SUIT_DETAIL, {"item_id": 35789}),
    ]


def test_import_by_ids_supports_emote_package():
    session = _Session({
        _key(EmoteUrls.PACKAGE, business="reply", ids="10239"): {"packages": [
            {"id": 10239, "text": "洛天依9th生日纪念 动态表情包", "emote": []},
        ]},
    })
    service = DressupService(session)

    item = service.import_by_ids(package_id="10239")

    assert item.kind == "emoji"
    assert item.name == "洛天依9th生日纪念 动态表情包"
    assert item.payload["id"] == 10239
    assert session.calls == [
        (EmoteUrls.PACKAGE, {"business": "reply", "ids": "10239"}),
    ]


def test_import_by_ids_emote_package_not_found_raises():
    session = _Session({
        _key(EmoteUrls.PACKAGE, business="reply", ids="999999"): {"packages": None},
    })

    with pytest.raises(ValueError, match="未找到表情包"):
        DressupService(session).import_by_ids(package_id="999999")


def test_import_by_ids_rejects_mixed_sources():
    with pytest.raises(ValueError, match="不能同时填写"):
        DressupService(_Session({})).import_by_ids(item_id="35789", package_id="10239")


def test_parse_direct_url_rejects_unknown_host_or_path():
    with pytest.raises(ValueError):
        DressupService.parse_direct_url("https://example.com/x/garb/v2/mall/suit/detail?item_id=1")
    with pytest.raises(ValueError):
        DressupService.parse_direct_url("https://api.bilibili.com/x/garb/v2/mall/suit/detail?item_id=0")
