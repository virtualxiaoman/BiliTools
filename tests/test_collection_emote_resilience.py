"""收藏集表情包接口异常时的下载回归测试。"""

from src.services.emote import EmoteService
from src.services.garb import GarbService


class _Session:
    def __init__(self, data=None):
        self.data = data
        self.session = type(
            "RequestsSession", (), {"headers": {"Referer": "https://www.bilibili.com/"}}
        )()

    def get(self, url, params=None):
        return self.data


def test_emote_package_null_means_no_accessible_packages():
    assert EmoteService(_Session({"packages": None})).get_packages(123) == []


def test_collection_still_downloads_other_resources_when_emote_lookup_fails(tmp_path, monkeypatch):
    item = {"name": "测试收藏集", "part_id": 0}
    detail = {
        "cover": "https://cdn.example.com/cover.jpg",
        "collect_list": {"collect_chain": [
            {"redeem_item_type_name": "表情包", "redeem_item_id": "123"},
        ]},
    }

    class BrokenEmoteService:
        def __init__(self, session):
            pass

        def count_emotes(self, package_ids):
            raise ValueError("表情包接口返回格式异常：packages 不是列表")

    calls = []

    def fake_download(url, path, headers=None, progress_cb=None):
        calls.append(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"cover")
        if progress_cb:
            progress_cb(1, 1)
        return 1

    monkeypatch.setattr("src.services.garb.EmoteService", BrokenEmoteService)
    monkeypatch.setattr("src.services.garb.download_stream", fake_download)

    results = GarbService(_Session()).download_item(item, tmp_path, detail=detail)

    assert [result.path.name for result in results] == ["封面.jpg"]
    assert calls == ["https://cdn.example.com/cover.jpg"]
