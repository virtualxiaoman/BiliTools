"""视频访问权限回归测试：充电专属视频不请求播放流，直接给出明确原因。"""
from pathlib import Path

import pytest

from src.api.errors import VideoChargingError, VideoPreviewOnlyError
from src.models.download_model import DashStreams, ProgressiveStream
from src.models.video_model import VideoInfo, VideoPage
from src.services.video import VideoService


def test_upower_exclusive_without_access_is_rejected(monkeypatch):
    service = VideoService(session=object())
    info = VideoInfo(
        bvid="BV1test",
        pages=[VideoPage(page=1, cid=123)],
        is_upower_exclusive=True,
        is_upower_play=False,
        is_upower_preview=True,
    )
    monkeypatch.setattr(service, "fetch_info", lambda bvid: info)
    playurl_calls = []
    monkeypatch.setattr(service, "get_playurl", lambda *args, **kwargs: playurl_calls.append(args))

    with pytest.raises(VideoChargingError):
        service._fetch_streams("BV1test")

    assert playurl_calls == []


def test_durl_only_playurl_is_preview_error(monkeypatch):
    class FakeSession:
        def get(self, url, params=None):
            return {"durl": [{"url": "https://example.invalid/preview.mp4"}]}

    import src.services.video as video_module
    monkeypatch.setattr(video_module, "get_wbi", lambda params: None)
    service = VideoService(session=FakeSession())

    with pytest.raises(VideoPreviewOnlyError):
        service.get_playurl("BV1test", 123)


def test_durl_full_length_is_progressive(monkeypatch):
    """老视频只有直出流、但时长与分P一致时，应作为可下载流返回（而非试看）。"""
    class FakeSession:
        def get(self, url, params=None):
            return {
                "quality": 80,
                "format": "mp4",
                "timelength": 7224280,
                "durl": [{"url": "https://example.invalid/full.mp4", "size": 100, "length": 7224280}],
            }

    import src.services.video as video_module
    monkeypatch.setattr(video_module, "get_wbi", lambda params: None)
    service = VideoService(session=FakeSession())

    dash = service.get_playurl("BV1test", 123, expected_duration=7231)

    assert isinstance(dash.progressive, ProgressiveStream)
    assert dash.progressive.urls == ["https://example.invalid/full.mp4"]
    assert dash.progressive.ext == "mp4"


def test_durl_shorter_than_page_is_preview_error(monkeypatch):
    """直出流明显短于分P时长时仍判定为试看流。"""
    class FakeSession:
        def get(self, url, params=None):
            return {
                "quality": 80,
                "format": "mp4",
                "durl": [{"url": "https://example.invalid/preview.mp4", "size": 10, "length": 300000}],
            }

    import src.services.video as video_module
    monkeypatch.setattr(video_module, "get_wbi", lambda params: None)
    service = VideoService(session=FakeSession())

    with pytest.raises(VideoPreviewOnlyError):
        service.get_playurl("BV1test", 123, expected_duration=7231)


def test_progressive_download_does_not_require_ffmpeg(tmp_path, monkeypatch):
    """直出流音视频合一，下载时不应要求 ffmpeg。"""
    from types import SimpleNamespace

    service = VideoService(session=SimpleNamespace(session=SimpleNamespace(headers={})))
    info = VideoInfo(bvid="BV1test", title="老视频", cid=1,
                     pages=[VideoPage(page=1, cid=1, part="P1", duration=7231)])
    stream = ProgressiveStream(urls=["https://example.invalid/full.mp4"], quality=80,
                               format="mp4", size=4)
    monkeypatch.setattr(service, "_fetch_streams",
                        lambda bvid, page, **kwargs: (info, DashStreams(progressive=stream), service))
    monkeypatch.setattr("src.services.video.ffmpeg_available", lambda: False)

    def fake_download(url, save_path, headers, **kwargs):
        Path(save_path).write_bytes(b"data")
        return 4

    monkeypatch.setattr("src.services.video.download_stream", fake_download)

    result = service.download_video_with_audio("BV1test", tmp_path, progress_cb=lambda *_: None)

    assert result.path.name == "老视频(BV1test).mp4"
    assert result.path.read_bytes() == b"data"
