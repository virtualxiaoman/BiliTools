"""多账号权限：大会员解析、充电换号、会员清晰度复核与清晰度上限。"""

import time

import pytest

from src.api.errors import VideoChargingError, VideoPreviewOnlyError
from src.models.download_model import (
    AudioStream,
    DashStreams,
    VideoQuality,
    VideoStream,
)
from src.models.login_model import LoginUser
from src.models.video_model import VideoInfo, VideoOwner, VideoPage
from src.services.account_capability import (
    AccountCapability,
    AccountPermissionCache,
    capability_for,
)
from src.services.video import VideoService


def _info(up_mid: int = 999, *, exclusive: bool = False, play: bool = True) -> VideoInfo:
    return VideoInfo(
        bvid="BV1test",
        title="测试视频",
        cid=123,
        owner=VideoOwner(mid=up_mid, name="UP"),
        pages=[VideoPage(page=1, cid=123, part="P1", duration=100)],
        is_upower_exclusive=exclusive,
        is_upower_play=play,
    )


def _dash(quality: int) -> DashStreams:
    return DashStreams(
        video=[VideoStream(url=f"http://v{quality}", quality=quality)],
        audio=[AudioStream(url="http://a")],
    )


class _SessionDouble:
    def __init__(self, path: str = "self.txt"):
        self.cookie_path = path
        self.closed = False
        self.session = type("_Inner", (), {"headers": {}})()

    def close(self):
        self.closed = True


class _FakeAccountService:
    """权限换号候选账号的最小服务替身。"""

    def __init__(self, info, dash, path="other.txt"):
        self._info = info
        self._dash = dash
        self.session = _SessionDouble(path)

    def fetch_info(self, bvid):
        return self._info

    def _resolve_page(self, info, page=1):
        return info.pages[0]

    def get_playurl(self, bvid, cid, expected_duration=0):
        return self._dash


# ---- 大会员状态 ----

def test_login_user_vip_by_status_and_due_date():
    future = int(time.time() * 1000) + 86400_000
    assert LoginUser.from_nav_json({"isLogin": True, "vipStatus": 1, "vipDueDate": future}).is_vip
    expired = int(time.time() * 1000) - 86400_000
    assert not LoginUser.from_nav_json({"vipStatus": 1, "vipDueDate": expired}).is_vip
    assert not LoginUser.from_nav_json({"vipStatus": 0, "vipDueDate": future}).is_vip


def test_permission_cache_roundtrip():
    cache = AccountPermissionCache()
    assert cache.upower_account(1) is None
    cache.remember_upower_account(1, "b.txt")
    assert cache.upower_account(1) == "b.txt"
    cache.remember_max_quality("BV1", 123, 80)
    assert cache.max_quality("BV1", 123) == 80


def test_capability_matches_by_mid_when_paths_differ():
    """当前账号 cookie 可能落在共享路径，能力匹配要能按 mid 命中。"""
    class Session:
        cookie_path = "global.txt"
        cookie = type("_Cookie", (), {"mid": 123})()

    caps = [AccountCapability(cookie_path="other.txt", uname="A", mid=123, is_vip=True)]
    assert capability_for(Session(), caps) is caps[0]


# ---- 充电换号 ----

def test_charging_falls_back_to_other_account(monkeypatch):
    service = VideoService(session=_SessionDouble())
    service.permission_accounts = [AccountCapability(cookie_path="other.txt", uname="账号B")]
    monkeypatch.setattr(service, "fetch_info", lambda bvid: _info(exclusive=True, play=False))

    candidate = _FakeAccountService(_info(exclusive=True, play=True), _dash(80))
    monkeypatch.setattr(service, "_permission_service", lambda cap: candidate)

    info, dash, stream_service = service._fetch_streams("BV1test")

    assert stream_service is candidate
    assert dash.best_video().quality == 80
    assert service.permission_cache.upower_account(999) == "other.txt"


def test_charging_skips_when_no_account_has_access(monkeypatch):
    service = VideoService(session=_SessionDouble())
    service.permission_accounts = [AccountCapability(cookie_path="other.txt", uname="账号B")]
    monkeypatch.setattr(service, "fetch_info", lambda bvid: _info(exclusive=True, play=False))

    candidate = _FakeAccountService(_info(exclusive=True, play=False), _dash(80))
    monkeypatch.setattr(service, "_permission_service", lambda cap: candidate)

    with pytest.raises(VideoChargingError):
        service._fetch_streams("BV1test")
    assert candidate.session.closed is True


def test_preview_only_falls_back_to_other_account(monkeypatch):
    service = VideoService(session=_SessionDouble())
    service.permission_accounts = [AccountCapability(cookie_path="other.txt", uname="账号B")]
    monkeypatch.setattr(service, "fetch_info", lambda bvid: _info())
    monkeypatch.setattr(service, "get_playurl", lambda *a, **k: (_ for _ in ()).throw(
        VideoPreviewOnlyError("preview")))

    candidate = _FakeAccountService(_info(), _dash(80))
    monkeypatch.setattr(service, "_permission_service", lambda cap: candidate)

    _, _, stream_service = service._fetch_streams("BV1test")
    assert stream_service is candidate


# ---- 会员清晰度复核 ----

def test_member_account_used_when_non_vip_gets_lower_quality(monkeypatch):
    service = VideoService(session=_SessionDouble())
    service.permission_accounts = [
        AccountCapability(cookie_path="self.txt", uname="账号A", is_vip=False),
        AccountCapability(cookie_path="vip.txt", uname="账号B", is_vip=True),
    ]
    monkeypatch.setattr(service, "fetch_info", lambda bvid: _info())
    monkeypatch.setattr(service, "get_playurl", lambda *a, **k: _dash(80))

    vip_service = _FakeAccountService(_info(), _dash(120), path="vip.txt")
    monkeypatch.setattr(service, "_permission_service",
                        lambda cap: vip_service if cap.cookie_path == "vip.txt" else None)

    info, dash, stream_service = service._fetch_streams("BV1test", quality=VideoQuality.HD4K)

    assert stream_service is vip_service
    assert dash.best_video().quality == 120
    assert service.permission_cache.max_quality("BV1test", 123) == 120


def test_no_member_probe_for_1080p_request(monkeypatch):
    service = VideoService(session=_SessionDouble())
    service.permission_accounts = [
        AccountCapability(cookie_path="self.txt", uname="账号A", is_vip=False),
        AccountCapability(cookie_path="vip.txt", uname="账号B", is_vip=True),
    ]
    monkeypatch.setattr(service, "fetch_info", lambda bvid: _info())
    monkeypatch.setattr(service, "get_playurl", lambda *a, **k: _dash(80))
    monkeypatch.setattr(service, "_permission_service",
                        lambda cap: pytest.fail("1080P 请求不应探测会员账号"))

    _, _, stream_service = service._fetch_streams("BV1test", quality=VideoQuality.P1080)
    assert stream_service is service


def test_member_probe_keeps_lower_quality_when_video_lacks_it(monkeypatch):
    """会员账号同样只有 1080P 时，认定视频本身没有更高档，不回退重试。"""
    service = VideoService(session=_SessionDouble())
    service.permission_accounts = [
        AccountCapability(cookie_path="self.txt", uname="账号A", is_vip=False),
        AccountCapability(cookie_path="vip.txt", uname="账号B", is_vip=True),
    ]
    monkeypatch.setattr(service, "fetch_info", lambda bvid: _info())
    monkeypatch.setattr(service, "get_playurl", lambda *a, **k: _dash(80))

    vip_service = _FakeAccountService(_info(), _dash(80), path="vip.txt")
    monkeypatch.setattr(service, "_permission_service", lambda cap: vip_service)

    _, dash, stream_service = service._fetch_streams("BV1test", quality=VideoQuality.HD4K)

    assert stream_service is service
    assert dash.best_video().quality == 80
    assert vip_service.session.closed is True
    assert service.permission_cache.max_quality("BV1test", 123) == 80


# ---- 清晰度上限 ----

def test_quality_cap_limits_non_vip_account():
    service = VideoService.__new__(VideoService)
    service.quality_cap = VideoQuality.P1080
    assert service._effective_quality(VideoQuality.HD4K) == VideoQuality.P1080
    assert service._effective_quality(VideoQuality.P720) == VideoQuality.P720


def test_cap_non_vip_quality_applies_only_to_non_vip():
    non_vip = VideoService(
        session=_SessionDouble("a.txt"),
        permission_accounts=[AccountCapability(cookie_path="a.txt", uname="A", is_vip=False)],
        cap_non_vip_quality=VideoQuality.P1080,
    )
    vip = VideoService(
        session=_SessionDouble("b.txt"),
        permission_accounts=[AccountCapability(cookie_path="b.txt", uname="B", is_vip=True)],
        cap_non_vip_quality=VideoQuality.P1080,
    )
    assert non_vip.quality_cap == VideoQuality.P1080
    assert vip.quality_cap is None


def test_capped_account_requests_1080p_stream(tmp_path, monkeypatch):
    """非会员账号（清晰度上限 1080P）即使任务请求 4K，也只按 1080P 取流下载。"""
    from pathlib import Path

    service = VideoService(session=_SessionDouble("a.txt"), quality_cap=VideoQuality.P1080)
    seen = {}

    def fake_fetch(bvid, page=1, quality=None):
        seen["quality"] = quality
        return _info(), _dash(80), service

    monkeypatch.setattr(service, "_fetch_streams", fake_fetch)
    monkeypatch.setattr("src.services.video.ffmpeg_available", lambda: True)
    monkeypatch.setattr("src.services.video.download_stream",
                        lambda url, save_path, headers, **kwargs: Path(save_path).write_bytes(b"x") or 1)
    monkeypatch.setattr("src.services.video.merge_video_audio",
                        lambda video, audio, save_path, **kwargs: Path(save_path).write_bytes(b"merged"))

    result = service.download_video_with_audio(
        "BV1test", tmp_path, quality=VideoQuality.HD4K, progress_cb=lambda *_: None)

    assert seen["quality"] == VideoQuality.P1080
    assert result.path.exists()
