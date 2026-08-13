"""前端下载路由接线测试（无网络、无 Qt 事件循环）。

验证 DownloadWorker._execute 把四种来源正确路由到 SDK 方法，
并始终传入 ProgressAdapter（进度信号来源）。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from frontend.pyside6.workers.download_worker import DownloadWorker  # noqa: E402

CALLS = []


class _Page:
    def __init__(self, page):
        self.page = page
        self.cid = page
        self.part = f"P{page}"


class _Ep:
    is_multi_page = False

    def __init__(self):
        self.pages = [_Page(1)]


class _Season:
    def __init__(self):
        self.title = "测试合集"
        self.episodes = [_Ep(), _Ep()]


class _FakeService:
    session = object()

    def _prog(self, value):
        return type(value).__name__

    def fetch_season(self, bvid=None, season_id=None, mid=0):
        CALLS.append(("fetch_season", bvid, season_id, mid))
        return _Season()

    def download_season(self, **kw):
        CALLS.append(("download_season", kw))
        return []

    def download_all_pages(self, bvid, dir, **kw):
        CALLS.append(("download_all_pages", bvid, dir, kw))
        return []

    def download_fav(self, fid, dir, **kw):
        CALLS.append(("download_fav", fid, dir, kw))
        return []

    def download_up(self, mid, dir, **kw):
        CALLS.append(("download_up", mid, dir, kw))
        return []

    def list_up_videos(self, mid):
        CALLS.append(("list_up_videos", mid))
        return ["BV1", "BV2"]

    def fetch_info(self, bvid):
        CALLS.append(("fetch_info", bvid))
        return type("Info", (), {"pages": [_Page(1), _Page(2)]})


class _FakeFavService:
    def __init__(self, session):
        pass

    def get_fav_bv(self, fid):
        CALLS.append(("get_fav_bv", fid))
        return ["BV1", "BV2", "BV3"]


@pytest.fixture(autouse=True)
def _reset():
    CALLS.clear()
    yield
    CALLS.clear()


def _worker(source, input_, **extra):
    spec = {
        "source": source, "input": input_, "scope": "all", "page": 1,
        "media_type": "video_with_audio", "quality": 120,
        "save_dir": "output/video", "desc": "test",
    }
    spec.update(extra)
    return DownloadWorker(spec)


def test_season_via_bvid():
    _worker("season", ("bvid", "BV1xxx", None))._execute(_FakeService())
    assert any(c[0] == "fetch_season" for c in CALLS)
    (name, kw), = [c for c in CALLS if c[0] == "download_season"]
    assert kw["progress"].__class__.__name__ == "ProgressAdapter"
    assert name == "download_season"


def test_season_via_sid():
    _worker("season", ("sid", 8683221, 12345))._execute(_FakeService())
    assert ("fetch_season", None, 8683221, 12345) in CALLS


def test_fav(monkeypatch):
    import frontend.pyside6.workers.download_worker as dw
    monkeypatch.setattr(dw, "FavService", _FakeFavService)
    _worker("fav", 3953119978)._execute(_FakeService())
    assert any(c[0] == "get_fav_bv" for c in CALLS)
    (_, fid, _dir, kw), = [c for c in CALLS if c[0] == "download_fav"]
    assert kw["progress"].__class__.__name__ == "ProgressAdapter"


def test_up():
    _worker("up", 249056021)._execute(_FakeService())
    assert any(c[0] == "list_up_videos" for c in CALLS)
    (_, mid, _dir, kw), = [c for c in CALLS if c[0] == "download_up"]
    assert kw["progress"].__class__.__name__ == "ProgressAdapter"


def test_bv_all_pages():
    _worker("bv", "BV1xxx", scope="all")._execute(_FakeService())
    (_, bvid, _dir, kw), = [c for c in CALLS if c[0] == "download_all_pages"]
    assert kw["progress"].__class__.__name__ == "ProgressAdapter"
