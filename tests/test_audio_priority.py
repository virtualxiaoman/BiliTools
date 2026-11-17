"""音频优先级：杜比/无损优先，失败回退 AAC。"""

import types
from pathlib import Path

import pytest

from src.api.errors import DownloadError
from src.models.download_model import (
    AudioStream,
    DashStreams,
    VideoQuality,
    VideoStream,
)
from src.models.video_model import VideoInfo, VideoPage
from src.services.video import VideoService, _audio_output_ext


def _service(tmp_path):
    service = VideoService(session=types.SimpleNamespace(
        session=types.SimpleNamespace(headers={})))
    service.default_dir = tmp_path
    return service


def _info():
    return VideoInfo(bvid="BV1test", title="测试", cid=1,
                     pages=[VideoPage(page=1, cid=1, part="P1", duration=10)])


def _dash(*audios):
    return DashStreams(
        video=[VideoStream(url="http://video", quality=120, codecs="avc1")],
        audio=list(audios),
    )


def test_audio_priority_and_output_ext():
    dolby = AudioStream(url="http://dolby", bandwidth=1_000_000, kind="dolby")
    flac = AudioStream(url="http://flac", bandwidth=1_600_000, kind="flac")
    aac = AudioStream(url="http://aac", bandwidth=192_000, kind="aac")
    dash = DashStreams(audio=[aac, flac, dolby])

    assert [stream.kind for stream in dash.audio_candidates()] == ["dolby", "flac", "aac"]
    assert dash.best_audio() is dolby
    assert _audio_output_ext(dolby) == "mka"
    assert _audio_output_ext(flac) == "flac"
    assert _audio_output_ext(aac) == "m4a"


def test_playurl_parses_dolby_and_flac(monkeypatch):
    class FakeSession:
        def get(self, url, params=None):
            return {"dash": {
                "video": [{"baseUrl": "http://video", "id": 120}],
                "audio": [{"baseUrl": "http://aac", "id": 30280, "bandwidth": 192000}],
                "dolby": {"type": 2, "audio": [
                    {"baseUrl": "http://dolby", "id": 30250, "bandwidth": 1000000, "codecs": "ec-3"},
                ]},
                "flac": {"display": True, "audio":
                    {"baseUrl": "http://flac", "id": 30251, "bandwidth": 1600000, "codecs": "fLaC"}},
            }}

    import src.services.video as video_module
    monkeypatch.setattr(video_module, "get_wbi", lambda params: None)

    dash = VideoService(session=FakeSession()).get_playurl("BV1test", 1)

    assert [stream.kind for stream in dash.audio_candidates()] == ["dolby", "flac", "aac"]
    assert dash.best_audio().url == "http://dolby"


def test_audio_download_falls_back_to_aac(tmp_path, monkeypatch):
    service = _service(tmp_path)
    dash = _dash(
        AudioStream(url="http://dolby", kind="dolby"),
        AudioStream(url="http://aac", kind="aac"),
    )
    monkeypatch.setattr(service, "_fetch_streams",
                        lambda bvid, page=1, quality=None: (_info(), dash, service))
    monkeypatch.setattr("src.services.video.ffmpeg_available", lambda: True)

    calls = []

    def fake_download(url, save_path, headers, **kwargs):
        calls.append(url)
        if url == "http://dolby":
            raise DownloadError("dolby cdn failed")
        Path(save_path).write_bytes(b"aac")
        return 3

    monkeypatch.setattr("src.services.video.download_stream", fake_download)

    result = service.download_audio("BV1test", tmp_path, progress_cb=lambda *_: None)

    assert calls == ["http://dolby", "http://aac"]
    assert result.path.suffix == ".m4a"
    assert result.path.read_bytes() == b"aac"


def test_video_download_falls_back_when_merge_fails(tmp_path, monkeypatch):
    service = _service(tmp_path)
    dash = _dash(
        AudioStream(url="http://dolby", kind="dolby"),
        AudioStream(url="http://aac", kind="aac"),
    )
    monkeypatch.setattr(service, "_fetch_streams",
                        lambda bvid, page=1, quality=None: (_info(), dash, service))
    monkeypatch.setattr("src.services.video.ffmpeg_available", lambda: True)

    def fake_download(url, save_path, headers, **kwargs):
        Path(save_path).write_bytes(url.encode())
        return 1

    merge_calls = []

    def fake_merge(video, audio, save_path, **kwargs):
        merge_calls.append(audio.name)
        if len(merge_calls) == 1:
            raise DownloadError("codec not supported in mp4")
        Path(save_path).write_bytes(b"merged")

    monkeypatch.setattr("src.services.video.download_stream", fake_download)
    monkeypatch.setattr("src.services.video.merge_video_audio", fake_merge)

    result = service.download_video_with_audio(
        "BV1test", tmp_path, quality=VideoQuality.HD4K, progress_cb=lambda *_: None)

    assert len(merge_calls) == 2  # 杜比合成失败 → 回退 AAC
    assert result.path.suffix == ".mp4"
    assert result.path.read_bytes() == b"merged"
