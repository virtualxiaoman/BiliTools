"""表情包服务的单元测试。"""

from src.services.emote import EmoteService
from src.urls.emote_urls import EmoteUrls


class _FakeSession:
    def __init__(self, packages):
        self.packages = packages
        self.session = type("RequestsSession", (), {"headers": {"Referer": "https://www.bilibili.com/"}})()
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return {"packages": self.packages}


def _dynamic_packages():
    return [{
        "id": 10238,
        "text": "洛天依14周年·纯蓝幻乐 动态表情包",
        "emote": [
            {
                "id": 1,
                "text": "[洛天依14周年·纯蓝幻乐 动态表情包_登场]",
                "url": "https://cdn.example.com/preview.png",
                "gif_url": "https://cdn.example.com/animated.gif?x=1",
                "meta": {"alias": "登场"},
            },
            {
                "id": 2,
                "text": "[洛天依14周年·纯蓝幻乐 动态表情包_静态]",
                "url": "https://cdn.example.com/static.png",
                "meta": {},
            },
        ],
    }]


def _fake_download(calls):
    def download(url, path, headers=None, progress_cb=None):
        calls.append((url, path, headers))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"ok")
        if progress_cb:
            progress_cb(2, 2)
        return 2

    return download


def test_normalize_package_ids_preserves_order_and_removes_duplicates():
    assert EmoteService.normalize_package_ids("10239, 10238,10239") == [10239, 10238]
    assert EmoteService.normalize_package_ids((10238, "10239")) == [10238, 10239]


def test_get_packages_uses_reply_business_and_comma_separated_ids():
    session = _FakeSession(_dynamic_packages())
    service = EmoteService(session)

    assert service.get_packages("10239,10238") == _dynamic_packages()
    assert session.calls == [
        (EmoteUrls.PACKAGE, {"business": "reply", "ids": "10239,10238"}),
    ]


def test_download_packages_prefers_gif_and_uses_collection_layout(tmp_path, monkeypatch):
    session = _FakeSession(_dynamic_packages())
    service = EmoteService(session)
    calls = []
    monkeypatch.setattr("src.services.emote.download_stream", _fake_download(calls))

    results = service.download_packages([10238], tmp_path)

    package_dir = tmp_path / "洛天依14周年·纯蓝幻乐" / "动态表情包"
    assert [result.path for result in results] == [
        package_dir / "登场.gif",
        package_dir / "静态.png",
    ]
    assert calls[0][0] == "https://cdn.example.com/animated.gif?x=1"
    assert calls[1][0] == "https://cdn.example.com/static.png"
    assert all(path.exists() for _, path, _ in calls)


def test_download_packages_uses_generic_package_folder_and_optional_full_name(tmp_path, monkeypatch):
    packages = [{
        "id": 10239,
        "text": "洛天依9th生日纪念",
        "emote": [{
            "id": 3,
            "text": "[洛天依9th生日纪念_比心]",
            "url": "https://cdn.example.com/static.png",
            "meta": {"alias": "比心"},
        }],
    }]
    calls = []
    monkeypatch.setattr("src.services.emote.download_stream", _fake_download(calls))
    service = EmoteService(_FakeSession(packages))

    results = service.download_packages(10239, tmp_path, use_full_name=True)

    assert results[0].path == (
        tmp_path / "洛天依9th生日纪念" / "表情包"
        / "洛天依9th生日纪念_比心.png"
    )


def test_default_directory_is_collection_output_root(tmp_path, monkeypatch):
    session = _FakeSession(_dynamic_packages())
    service = EmoteService(session, default_dir=tmp_path / "output" / "收藏集")
    calls = []
    monkeypatch.setattr("src.services.emote.download_stream", _fake_download(calls))

    results = service.download_packages(10238)

    assert results[0].path.parent == (
        tmp_path / "output" / "收藏集" / "洛天依14周年·纯蓝幻乐" / "动态表情包"
    )
