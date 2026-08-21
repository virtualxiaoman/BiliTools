"""装扮统一服务：三类搜索合并 + 批量并发下载。"""

from pathlib import Path

from src.models.download_model import DownloadResult
from src.services.dressup import DressupItem, DressupService
from src.urls.emote_urls import EmoteUrls
from src.urls.garb_urls import GarbUrls


class _FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.session = type(
            "RequestsSession", (), {"headers": {"Referer": "https://www.bilibili.com/"}}
        )()

    def get(self, url, params=None):
        self.calls.append((url, params))
        key = url, tuple(sorted((params or {}).items()))
        return self.responses[key]


def _key(url, **params):
    return url, tuple(sorted(params.items()))


def test_search_combines_emoji_collection_and_suit():
    session = _FakeSession({
        _key(GarbUrls.SEARCH, key_word="洛天依", pn=1, ps=50): {"list": [
            {"name": "洛天依14周年·纯蓝幻乐", "part_id": 0, "properties": {}},
            {"name": "纯蓝幻乐装扮", "part_id": 6, "item_id": 123},
        ]},
        _key(EmoteUrls.SEARCH, business="reply", key_word="洛天依", pn=1, ps=50): {"list": [
            {"id": 10239, "text": "洛天依9th生日纪念"},
        ]},
    })

    items = DressupService(session).search("洛天依")

    assert [item.kind for item in items] == ["emoji", "collection", "suit"]
    assert items[0].display_name == "表情包-洛天依9th生日纪念"
    assert items[1].display_name == "收藏集-洛天依14周年·纯蓝幻乐"
    assert items[2].display_name == "装扮-纯蓝幻乐装扮"
    assert [url for url, _ in session.calls] == [GarbUrls.SEARCH, EmoteUrls.SEARCH]


class _FakeEmoteService:
    instances = []

    def __init__(self, session, default_dir=None):
        self.session = session
        self.default_dir = default_dir
        self.instances.append((session, default_dir))

    def download_packages(self, package_ids, directory, **kwargs):
        return [DownloadResult(
            Path(directory) / f"emoji-{package_ids[0]}.png", media_type="emote", size=1,
        )]


class _FakeGarbService:
    instances = []

    def __init__(self, session, default_dir=None):
        self.session = session
        self.default_dir = default_dir
        self.instances.append((session, default_dir))

    def download_item(self, item, directory, **kwargs):
        return [DownloadResult(
            Path(directory) / f"{item['name']}.png", media_type="garb", size=1,
        )]


def test_download_items_supports_concurrency_and_account_distribution(tmp_path, monkeypatch):
    monkeypatch.setattr("src.services.dressup.EmoteService", _FakeEmoteService)
    monkeypatch.setattr("src.services.dressup.GarbService", _FakeGarbService)
    _FakeEmoteService.instances = []
    _FakeGarbService.instances = []

    account_a = object()
    account_b = object()
    items = [
        DressupItem("emoji", "表情包A", {"id": 1}),
        DressupItem("collection", "收藏集A", {"name": "收藏集A"}),
    ]

    results = DressupService(_FakeSession({})).download_items(
        items, tmp_path, threads=2, account_sessions=[account_a, account_b],
    )

    assert len(results) == 2
    assert {path.name for path in (_r.path for _r in results)} == {
        "emoji-1.png", "收藏集A.png",
    }
    assert {s for s, _ in _FakeEmoteService.instances + _FakeGarbService.instances} == {
        account_a, account_b,
    }


def test_download_items_sequential_uses_current_session(tmp_path, monkeypatch):
    monkeypatch.setattr("src.services.dressup.EmoteService", _FakeEmoteService)
    _FakeEmoteService.instances = []
    session = _FakeSession({})

    results = DressupService(session).download_items(
        [DressupItem("emoji", "表情包B", {"id": 2})],
        tmp_path,
        threads=1,
    )

    assert results[0].path.name == "emoji-2.png"
    assert _FakeEmoteService.instances[0][0] is session
