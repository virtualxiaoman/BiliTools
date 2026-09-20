"""收藏集奖励链表情包下载回归测试。"""

from src.models.download_model import DownloadResult
from src.services.garb import GarbService
from src.urls.garb_urls import GarbUrls


class _FakeSession:
    def __init__(self, item=None, detail=None):
        self.item = item
        self.detail = detail
        self.session = type(
            "RequestsSession", (), {"headers": {"Referer": "https://www.bilibili.com/"}}
        )()

    def get(self, url, params=None):
        if url == GarbUrls.SEARCH:
            return {"list": [self.item]}
        if url == GarbUrls.COLLECTION_DETAIL:
            return self.detail
        raise AssertionError(f"Unexpected request: {url}, {params}")


def _fake_download(calls):
    def download(url, path, headers=None, progress_cb=None):
        calls.append((url, path, headers))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"cover")
        if progress_cb:
            progress_cb(1, 1)
        return 1

    return download


def test_collection_downloads_emotes_from_collect_chain_and_reuses_prepared_packages(tmp_path, monkeypatch):
    item = {
        "name": "测试收藏集",
        "part_id": 0,
        "properties": {"dlc_act_id": "111", "dlc_lottery_id": "222"},
    }
    detail = {
        "cover": "https://cdn.example.com/cover.jpg",
        "collect_list": {
            "collect_chain": [
                {"redeem_item_type_name": "表情包", "redeem_item_id": "101"},
                {"redeem_item_type_name": "动态表情包", "redeem_item_id": "102"},
                {"redeem_item_type_name": "表情包", "redeem_item_id": "101"},
                {"redeem_item_type_name": "装扮", "redeem_item_id": "103"},
                {"redeem_item_type_name": "表情包", "redeem_item_id": "103&104"},
            ]
        },
    }
    packages = [
        {"id": 101, "text": "测试收藏集 静态表情包", "emote": [{"id": 1}]},
        {"id": 102, "text": "测试收藏集 动态表情包", "emote": [{"id": 2}, {"id": 3}]},
    ]
    calls = {"count": [], "download": []}
    fake_session = _FakeSession(item, detail)

    class FakeEmoteService:
        def __init__(self, session):
            assert session is fake_session

        def count_emotes(self, package_ids):
            calls["count"].append(list(package_ids))
            return packages, 3

        def download_packages(self, package_ids, directory, *, progress, progress_cb, packages):
            calls["download"].append((list(package_ids), directory, packages))
            results = []
            for index, name in enumerate(("静态.png", "动态1.gif", "动态2.gif"), 1):
                progress.start(index, name)
                progress.finish()
                progress_cb(index, 3)
                path = tmp_path / "测试收藏集" / "表情包" / name
                results.append(DownloadResult(path, media_type="emote", size=1))
            return results

    media_calls = []
    progress_calls = []
    monkeypatch.setattr("src.services.garb.EmoteService", FakeEmoteService)
    monkeypatch.setattr("src.services.garb.download_stream", _fake_download(media_calls))
    service = GarbService(fake_session)

    prepared_item, prepared_detail, count = service.prepare_download("测试收藏集")
    results = service.download_item(
        prepared_item, tmp_path, detail=prepared_detail, progress_cb=lambda index, total: progress_calls.append((index, total)),
    )

    assert count == 4
    assert calls["count"] == [[101, 102]]
    assert calls["download"] == [([101, 102], tmp_path, packages)]
    assert [result.path.name for result in results] == ["封面.jpg", "静态.png", "动态1.gif", "动态2.gif"]
    assert [url for url, _, _ in media_calls] == ["https://cdn.example.com/cover.jpg"]
    assert progress_calls == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_collection_emoji_package_filter_downloads_only_linked_emotes(tmp_path, monkeypatch):
    item = {"name": "测试收藏集", "part_id": 0}
    detail = {
        "cover": "https://cdn.example.com/cover.jpg",
        "collect_list": {"collect_chain": [
            {"redeem_item_type_name": "表情包", "redeem_item_id": "101"},
        ]},
    }

    class FakeEmoteService:
        def __init__(self, session):
            pass

        def count_emotes(self, package_ids):
            return [{"id": 101, "emote": [{"id": 1}]}], 1

        def download_packages(self, package_ids, directory, **kwargs):
            return [DownloadResult(tmp_path / "表情包" / "表情.png", media_type="emote", size=1)]

    media_calls = []
    monkeypatch.setattr("src.services.garb.EmoteService", FakeEmoteService)
    monkeypatch.setattr("src.services.garb.download_stream", _fake_download(media_calls))

    results = GarbService(_FakeSession()).download_item(
        item, tmp_path, detail=detail, resource_types="emoji_package",
    )

    assert [result.media_type for result in results] == ["emote"]
    assert media_calls == []
