"""download_fav / download_up / download_season 复用外部列表/合集结构的单元测试。

背景：GUI worker 会先取列表（收藏夹/UP主）或合集结构用于进度总数，
再调用对应下载方法。为避免重复 API 请求，这三个方法新增了可选的
`bvids` / `season` 参数——传入时跳过内部拉取，不传时保持原有行为。

回归点：
1. 传入外部列表 → 内部不再重复拉取（get_fav_bv / list_up_videos / fetch_season 不调用）；
2. 不传外部列表 → 与之前完全一致（内部自动获取一次）。
"""

import pytest

from src.services import VideoService


def _svc(tmp_path):
    """构造不联网的 VideoService（绕过 __init__，不读 cookie、不发请求）。"""
    svc = VideoService.__new__(VideoService)
    svc.session = object()
    svc.default_dir = tmp_path
    return svc


class _Page:
    def __init__(self):
        self.page = 1
        self.cid = 1
        self.part = "P1"


class _Episode:
    is_multi_page = False

    def __init__(self):
        self.bvid = "BV1"
        self.title = "稿件"
        self.pages = [_Page()]


class _Season:
    def __init__(self):
        self.id = 8683221
        self.title = "测试合集"
        self.episodes = [_Episode()]


class _FavInfo:
    title = "测试收藏夹"


def test_download_fav_reuses_external_bvids(tmp_path, monkeypatch):
    """传入 bvids 时，内部不应再调用 get_fav_bv。"""
    svc = _svc(tmp_path)
    svc.download_all_pages = lambda *a, **k: []  # 不触发网络

    calls = {"get_fav_bv": 0}

    class FakeFav:
        def __init__(self, session):
            pass

        def get_fav_info(self, fid):
            return _FavInfo()

        def get_fav_bv(self, fid):
            calls["get_fav_bv"] += 1
            return ["BV1"]

    # download_fav 内部是 `from src.services.fav import FavService`，须 patch 该模块
    monkeypatch.setattr("src.services.fav.FavService", FakeFav)

    svc.download_fav(1, tmp_path, mode="audio", bvids=["BV1"])
    assert calls["get_fav_bv"] == 0  # 复用外部列表，不再内部拉取


def test_download_fav_fetches_when_no_bvids(tmp_path, monkeypatch):
    """未传 bvids 时保持原有行为：内部自动获取列表。"""
    svc = _svc(tmp_path)
    svc.download_all_pages = lambda *a, **k: []

    calls = {"get_fav_bv": 0}

    class FakeFav:
        def __init__(self, session):
            pass

        def get_fav_info(self, fid):
            return _FavInfo()

        def get_fav_bv(self, fid):
            calls["get_fav_bv"] += 1
            return ["BV1"]

    monkeypatch.setattr("src.services.fav.FavService", FakeFav)

    svc.download_fav(1, tmp_path, mode="audio")
    assert calls["get_fav_bv"] == 1  # 内部自动获取一次


def test_download_up_reuses_external_bvids(tmp_path, monkeypatch):
    """传入 bvids 时，内部不应再调用 list_up_videos（避免整页遍历两遍）。"""
    svc = _svc(tmp_path)
    svc.download_all_pages = lambda *a, **k: []
    svc._resolve_mid = lambda mid: 1

    calls = {"list_up_videos": 0}

    def fake_list(mid):
        calls["list_up_videos"] += 1
        return ["BV1"]

    svc.list_up_videos = fake_list

    class FakeUser:
        def __init__(self, session):
            pass

        def get_name(self, mid):
            return "测试UP"

    monkeypatch.setattr("src.services.user.UserService", FakeUser)

    svc.download_up(1, tmp_path, mode="audio", bvids=["BV1"])
    assert calls["list_up_videos"] == 0  # 复用外部列表，不再翻页

    svc.download_up(1, tmp_path, mode="audio")
    assert calls["list_up_videos"] == 1  # 未传列表时保持原有行为


def test_download_season_reuses_external_season(tmp_path):
    """传入 season 时，内部不应再调用 fetch_season 反查合集。"""
    svc = _svc(tmp_path)
    svc._download_episode = lambda ep, save_dir, **k: ([], 1)  # 不触发网络

    calls = {"fetch_season": 0}

    def fake_fetch_season(bvid=None, season_id=None, mid=0):
        calls["fetch_season"] += 1
        return _Season()

    svc.fetch_season = fake_fetch_season

    svc.download_season(season_id=8683221, dir=tmp_path, season=_Season())
    assert calls["fetch_season"] == 0  # 复用外部合集结构，不再反查

    svc.download_season(season_id=8683221, dir=tmp_path)
    assert calls["fetch_season"] == 1  # 未传时保持原有行为


# ---- 并发下载（threads>1）----


class _Episode3:
    is_multi_page = False

    def __init__(self, bvid):
        self.bvid = bvid
        self.title = f"稿件{bvid}"
        self.pages = [_Page()]


class _Season3:
    id = 1
    title = "测试合集"
    episodes = [_Episode3("BV1"), _Episode3("BV2"), _Episode3("BV3")]


def test_download_season_parallel_uses_multiple_threads(tmp_path):
    """threads>1 时应并发下载稿件，结果按输入顺序汇总。"""
    import threading
    import time

    svc = _svc(tmp_path)
    svc.fetch_season = lambda bvid=None, season_id=None, mid=0: _Season3()
    svc._report_bvid_download = lambda bvid, new_results, dc, i, total: dc  # 跳过节流

    threads_seen = set()
    lock = threading.Lock()

    def fake_episode(ep, save_dir, **k):
        with lock:
            threads_seen.add(threading.get_ident())
        time.sleep(0.05)  # 制造并发窗口
        return ([ep.bvid], 1)

    svc._download_episode = fake_episode

    results = svc.download_season(season_id=1, dir=tmp_path, threads=2)
    assert results == ["BV1", "BV2", "BV3"]  # 顺序汇总
    assert len(threads_seen) >= 2  # 确实起了多个线程并发


def test_download_fav_parallel_threads(tmp_path):
    """threads>1 时收藏夹也走并发路径。"""
    import threading
    import time

    svc = _svc(tmp_path)
    svc.download_all_pages = lambda *a, **k: ["OK"]
    svc._report_bvid_download = lambda bvid, new_results, dc, i, total: dc

    threads_seen = set()
    lock = threading.Lock()

    def fake_episode(bvid, save_dir, **k):
        with lock:
            threads_seen.add(threading.get_ident())
        time.sleep(0.05)
        return ["OK"]

    # 直接替换 download_all_pages，观察并发
    svc.download_all_pages = fake_episode

    class FakeFav:
        def __init__(self, session):
            pass

        def get_fav_info(self, fid):
            return _FavInfo()

        def get_fav_bv(self, fid):
            return ["BV1", "BV2", "BV3"]

    monkeypatch = __import__("pytest").MonkeyPatch()
    try:
        monkeypatch.setattr("src.services.fav.FavService", FakeFav)
        results = svc.download_fav(1, tmp_path, mode="video", threads=2)
    finally:
        monkeypatch.undo()
    assert results == ["OK", "OK", "OK"]
    assert len(threads_seen) >= 2


def test_download_fav_distributes_across_accounts(tmp_path, monkeypatch):
    """account_sessions 非空时，并发任务均匀轮询分摊到各账号（BV1/BV3→s1，BV2/BV4→s2）。"""
    from src.services import VideoService

    svc = _svc(tmp_path)
    svc._report_bvid_download = lambda bvid, new_results, dc, i, total: dc

    class FakeFav:
        def __init__(self, session):
            pass

        def get_fav_info(self, fid):
            return _FavInfo()

        def get_fav_bv(self, fid):
            return ["BV1", "BV2", "BV3", "BV4"]

    monkeypatch.setattr("src.services.fav.FavService", FakeFav)

    got = {}

    def fake_download_all_pages(self, *a, **k):
        got.setdefault(id(self.session), []).append(a[0])
        return []

    monkeypatch.setattr(VideoService, "download_all_pages", fake_download_all_pages)

    s1, s2 = object(), object()
    svc.download_fav(1, tmp_path, mode="video", threads=2, account_sessions=[s1, s2])

    # 任务按下标轮询：i%2 → 0,2 走 s1；1,3 走 s2
    assert sorted(got[id(s1)]) == ["BV1", "BV3"]
    assert sorted(got[id(s2)]) == ["BV2", "BV4"]


def test_download_fav_no_accounts_uses_current(tmp_path, monkeypatch):
    """account_sessions 为空时，并发任务全部使用当前 service（回退行为）。"""
    from src.services import VideoService

    svc = _svc(tmp_path)
    svc._report_bvid_download = lambda bvid, new_results, dc, i, total: dc

    class FakeFav:
        def __init__(self, session):
            pass

        def get_fav_info(self, fid):
            return _FavInfo()

        def get_fav_bv(self, fid):
            return ["BV1", "BV2"]

    monkeypatch.setattr("src.services.fav.FavService", FakeFav)

    used = []

    def fake_download_all_pages(self, *a, **k):
        used.append(self is svc)  # 应使用原 service 自身
        return []

    monkeypatch.setattr(VideoService, "download_all_pages", fake_download_all_pages)

    svc.download_fav(1, tmp_path, mode="video", threads=2)
    assert used == [True, True]  # 两个任务都在原 service 上执行
