"""视频访问权限回归测试：充电专属视频不请求播放流，直接给出明确原因。"""
import threading
from pathlib import Path

import pytest

from src.api.errors import (
    DownloadCancelled,
    DownloadError,
    FFmpegNotFoundError,
    VideoChargingError,
    VideoPreviewOnlyError,
)
from src.models.download_model import DashStreams, ProgressiveStream
from src.models.video_model import VideoInfo, VideoPage
from src.services.video import _RETRY_OUTCOME, VideoService


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


# ---- 批量任务的单文件失败处理 ----

def _raising_action(exc: Exception):
    def action():
        raise exc
    return action


def test_batch_skips_single_file_download_error():
    """CDN 超时等单文件下载失败只标记为待重试，不中断整个批量任务。"""
    service = VideoService(session=object())
    outcome = service._execute_batch_download(
        "BV1test", _raising_action(DownloadError("Read timed out")), label="UP主")
    assert outcome is _RETRY_OUTCOME


def test_batch_still_fails_when_ffmpeg_missing():
    service = VideoService(session=object())
    with pytest.raises(FFmpegNotFoundError):
        service._execute_batch_download(
            "BV1test", _raising_action(FFmpegNotFoundError("no ffmpeg")), label="UP主")


def test_batch_does_not_swallow_cancel():
    service = VideoService(session=object())
    service.cancel_event = threading.Event()
    service.cancel_event.set()
    with pytest.raises(DownloadCancelled):
        service._execute_batch_download(
            "BV1test", _raising_action(DownloadCancelled("下载已取消")), label="UP主")


# ---- 分P级重试队列与终止 ----

def test_batch_retry_queues_only_failed_pages(tmp_path, monkeypatch):
    """批量队列以分P为单位：只把失败的分P排到队尾重试。"""
    from src.models.download_model import VideoQuality
    from src.util.progress import BatchProgress

    service = VideoService(session=object())
    service.default_dir = tmp_path
    calls = []

    def fake_report(bvid, dir=None, **kwargs):
        calls.append(kwargs.get("only_pages"))
        if kwargs.get("only_pages") is None:
            return [], [2]
        return ["ok"], []

    monkeypatch.setattr(service, "_download_all_pages_report", fake_report)
    monkeypatch.setattr(service, "_report_bvid_download", lambda *a, **k: 0)

    results = service._download_bvid_collection(
        ["BV1"], tmp_path, quality=VideoQuality.P1080, media_type="video_with_audio",
        progress=BatchProgress(n=1), progress_cb=None, threads=1, account_sessions=None,
        cache_dirs=None, force=False, item_label=lambda bvid: "UP主",
    )

    assert calls == [None, [2]]
    assert results == ["ok"]


def test_collection_stops_when_cancelled(tmp_path, monkeypatch):
    """终止后不再开始新的视频。"""
    from src.models.download_model import VideoQuality
    from src.util.progress import BatchProgress

    service = VideoService(session=object())
    service.default_dir = tmp_path
    service.cancel_event = threading.Event()
    service.cancel_event.set()
    called = []
    monkeypatch.setattr(service, "_download_all_pages_report",
                        lambda *a, **k: called.append(1) or ([], []))

    with pytest.raises(DownloadCancelled):
        service._download_bvid_collection(
            ["BV1", "BV2"], tmp_path, quality=VideoQuality.P1080,
            media_type="video_with_audio", progress=BatchProgress(n=2),
            progress_cb=None, threads=1, account_sessions=None,
            cache_dirs=None, force=False, item_label=lambda bvid: "UP主",
        )
    assert called == []


def test_page_download_reports_bytes_to_external_progress(tmp_path, monkeypatch):
    """外部进度对象必须收到真实字节；否则会把刚下完的文件误报为“已存在”。"""
    import types

    from frontend.pyside6.workers.progress_adapter import ProgressAdapter
    from src.models.download_model import AudioStream, DashStreams, VideoStream
    from src.models.video_model import VideoInfo, VideoPage

    messages = []

    class _Signal:
        def emit(self, *args):
            pass

    class _Worker:
        def __init__(self):
            self.progress = _Signal()
            self.phase = _Signal()

        def milestone(self, category, text):
            messages.append(text)

    service = VideoService(session=types.SimpleNamespace(
        session=types.SimpleNamespace(headers={})))
    service.default_dir = tmp_path
    info = VideoInfo(bvid="BV1test", title="测试", cid=1,
                     pages=[VideoPage(page=1, cid=1, part="P1", duration=10)])
    dash = DashStreams(video=[VideoStream(url="http://v", quality=80, codecs="avc1")],
                       audio=[AudioStream(url="http://a", codecs="mp4a")])
    monkeypatch.setattr(service, "fetch_info", lambda bvid: info)
    monkeypatch.setattr(service, "_fetch_streams",
                        lambda bvid, page=1, quality=None: (info, dash, service))

    def fake_download(url, save_path, headers, progress_cb=None, **kwargs):
        if progress_cb:
            progress_cb(30, 30)
        Path(save_path).write_bytes(b"x")
        return 1

    monkeypatch.setattr("src.services.video.download_stream", fake_download)

    adapter = ProgressAdapter(1, "测试", _Worker())
    service._download_all_pages_report("BV1test", tmp_path, media_type="video", progress=adapter)

    assert adapter.current_done == 30
    assert any(text.startswith("下载完成") for text in messages)
    assert not any(text.startswith("已存在，跳过") for text in messages)


def test_batch_skips_only_up_visible_and_auditing():
    """62012/62004/-404 都不应中断批量任务，只跳过当前视频。"""
    from src.api.errors import BiliAPIError

    service = VideoService(session=object())
    for code in (-404, 62002, 62004, 62012):
        outcome = service._execute_batch_download(
            "BV1test", _raising_action(BiliAPIError(code, str(code))), label="UP主")
        assert outcome is None
