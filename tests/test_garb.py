"""收藏集（DLC）与装扮下载服务的单元测试。"""

import pytest

from src.services.garb import GarbService
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
        return self.responses[(url, tuple(sorted((params or {}).items())))]


def _key(url, **params):
    return url, tuple(sorted(params.items()))


def _fake_download(calls):
    def download(url, path, headers=None, progress_cb=None):
        calls.append((url, path, headers))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"ok")
        if progress_cb:
            progress_cb(2, 2)
        return 2

    return download


def test_collection_uses_search_and_detail_contracts(tmp_path, monkeypatch):
    item = {
        "name": "测试收藏集",
        "part_id": 0,
        "properties": {"dlc_act_id": "111", "dlc_lottery_id": "222"},
    }
    detail = {
        "cover": "https://cdn.example.com/cover.jpg",
        "item_list": [{"card_info": {
            "card_name": "夜行奇术师",
            "card_img": "https://cdn.example.com/card.png",
            "video_list": ["https://cdn.example.com/card.mp4?token=1"],
        }}],
    }
    session = _FakeSession({
        _key(GarbUrls.SEARCH, key_word="测试收藏集", pn=1, ps=20): {"list": [item]},
        _key(GarbUrls.COLLECTION_DETAIL, act_id="111", lottery_id="222"): detail,
    })
    calls = []
    monkeypatch.setattr("src.services.garb.download_stream", _fake_download(calls))

    results = GarbService(session).download_by_keyword("测试收藏集", tmp_path)

    root = tmp_path / "测试收藏集"
    assert [result.path for result in results] == [
        root / "封面.jpg", root / "夜行奇术师.png", root / "夜行奇术师.mp4",
    ]
    assert session.calls == [
        (GarbUrls.SEARCH, {"key_word": "测试收藏集", "pn": 1, "ps": 20}),
        (GarbUrls.COLLECTION_DETAIL, {"act_id": "111", "lottery_id": "222"}),
    ]
    assert [url for url, _, _ in calls] == [
        "https://cdn.example.com/cover.jpg",
        "https://cdn.example.com/card.png",
        "https://cdn.example.com/card.mp4?token=1",
    ]


def test_suit_resources_use_category_directories_and_short_emoji_names(tmp_path, monkeypatch):
    item = {"name": "测试装扮", "part_id": 1, "item_id": 418043001}
    detail = {"suit_items": {
        "card": [{"name": "粉丝卡", "properties": {
            "image": "https://cdn.example.com/card.png",
            "fans_image": "https://cdn.example.com/card-fans.png",
        }}],
        "emoji_package": [{"items": [{"name": "[测试装扮_登场]", "properties": {
            "image": "https://cdn.example.com/entry.gif",
        }}]}],
        "loading": [{"name": "加载", "properties": {
            "loading_url": "https://cdn.example.com/loading.webp",
            "loading_frame_url": "https://cdn.example.com/frame.png",
        }}],
        "space_bg": [{"name": "空间", "properties": {
            "image1_landscape": "https://cdn.example.com/space-landscape.jpg",
        }}],
    }}
    session = _FakeSession({
        _key(GarbUrls.SUIT_DETAIL, item_id=418043001): detail,
    })
    calls = []
    monkeypatch.setattr("src.services.garb.download_stream", _fake_download(calls))

    results = GarbService(session).download_item(item, tmp_path)

    root = tmp_path / "测试装扮"
    assert [result.path for result in results] == [
        root / "动态卡片" / "粉丝卡.png",
        root / "动态卡片" / "粉丝卡_fans.png",
        root / "表情包" / "登场.gif",
        root / "加载动画" / "加载.webp",
        root / "加载动画" / "加载_frame.png",
        root / "空间海报" / "空间_1_landscape.jpg",
    ]
    assert session.calls == [(GarbUrls.SUIT_DETAIL, {"item_id": 418043001})]


def test_resource_type_filter_cache_and_invalid_category(tmp_path, monkeypatch):
    item = {"name": "测试收藏集", "part_id": 0}
    detail = {"cover": "https://cdn.example.com/cover.jpg"}
    session = _FakeSession({})
    service = GarbService(session)
    cached_path = tmp_path / "测试收藏集" / "封面.jpg"
    cached_path.parent.mkdir(parents=True)
    cached_path.write_bytes(b"cached")
    calls = []
    monkeypatch.setattr("src.services.garb.download_stream", _fake_download(calls))

    results = service.download_item(item, tmp_path, detail=detail, resource_types="cover")

    assert results[0].path == cached_path
    assert results[0].cached is True
    assert calls == []
    with pytest.raises(ValueError, match="不支持的资源类型"):
        service.list_resources(item, detail, resource_types=["emoji_package"])
