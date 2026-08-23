from pathlib import Path
"""VideoService 缓存判断单元测试（无网络）。

回归：仅音频下载时，已存在的「视频」mp4 不应被当作音频已下载而跳过。
"""
from src.services.video import VideoService


def _service(tmp_path) -> VideoService:
    # 绕过 __init__（不构造 BiliSession，避免读 cookie / 发网络请求）
    svc = VideoService.__new__(VideoService)
    svc.default_dir = tmp_path
    return svc


def test_video_mp4_not_counted_as_cached_audio(tmp_path):
    """已存在视频 mp4 → 音频缓存检查应命中 None（需重新下载音频）。"""
    svc = _service(tmp_path)
    (tmp_path / "标题(BV1ov42117yC).mp4").write_bytes(b"x")
    assert svc._find_downloaded_file("BV1ov42117yC", {"m4a", "mp3", "flac", "aac"}) is None
    # 视频缓存检查应命中（该 mp4 确实是视频）
    assert svc._find_downloaded_file("BV1ov42117yC", {"mp4", "flv", "m4s"}) is not None


def test_audio_file_counted_as_cached_audio(tmp_path):
    """已存在音频 m4a → 音频缓存检查应命中。"""
    svc = _service(tmp_path)
    (tmp_path / "标题(BV1ov42117yC).m4a").write_bytes(b"x")
    assert svc._find_downloaded_file("BV1ov42117yC", {"m4a", "mp3", "flac", "aac"}) is not None


def test_audio_not_counted_as_cached_video(tmp_path):
    """已存在音频 m4a → 视频缓存检查应命中 None（无视频文件）。"""
    svc = _service(tmp_path)
    (tmp_path / "标题(BV1ov42117yC).m4a").write_bytes(b"x")
    assert svc._find_downloaded_file("BV1ov42117yC", {"mp4", "flv", "m4s"}) is None



def test_cache_lookup_checks_current_and_extra_directories(tmp_path):
    """缓存目录列表包含当前下载目录，并可命中额外目录。"""
    svc = _service(tmp_path / "current")
    extra = tmp_path / "archive"
    extra.mkdir()
    cached = extra / "旧标题(BVcache123).mp4"
    cached.write_bytes(b"cached")

    found = svc._find_downloaded_file(
        "BVcache123", {"mp4"}, roots=svc._cache_roots(tmp_path / "current", [extra])
    )
    assert found == cached


def test_cache_lookup_prefers_current_directory(tmp_path):
    """当前下载目录与额外目录同时命中时，优先使用当前目录。"""
    current = tmp_path / "current"
    extra = tmp_path / "archive"
    current.mkdir()
    extra.mkdir()
    current_file = current / "当前标题(BVcache456).mp4"
    extra_file = extra / "旧标题(BVcache456).mp4"
    current_file.write_bytes(b"current")
    extra_file.write_bytes(b"extra")

    svc = _service(current)
    assert svc._find_downloaded_file(
        "BVcache456", {"mp4"}, roots=svc._cache_roots(current, [extra])
    ) == current_file



def test_force_download_overwrites_exact_target_but_keeps_different_name(tmp_path, monkeypatch):
    """force 忽略缓存；同名目标覆盖，旧目录中不同文件名仍保留。"""
    from types import SimpleNamespace
    from src.models.download_model import DashStreams, VideoStream
    from src.models.video_model import VideoInfo

    svc = _service(tmp_path / "current")
    svc.session = SimpleNamespace(session=SimpleNamespace(headers={}))
    info = VideoInfo(bvid="BVforce123", title="新标题", cid=1, pages=[])
    stream = VideoStream(url="http://stream", codecs="avc1", quality=80)
    svc._fetch_streams = lambda bvid, page: (info, DashStreams(video=[stream], audio=[]))

    old = tmp_path / "archive" / "旧标题(BVforce123).mp4"
    old.parent.mkdir()
    old.write_bytes(b"old")
    target = tmp_path / "current" / "新标题(BVforce123).mp4"
    target.parent.mkdir()
    target.write_bytes(b"before")

    calls = []
    def fake_download(url, save_path, headers, **kwargs):
        calls.append(kwargs)
        Path(save_path).write_bytes(b"after")
        return 5

    monkeypatch.setattr("src.services.video.download_stream", fake_download)
    result = svc.download_video(
        "BVforce123", tmp_path / "current", cache_dirs=[old.parent], force=True,
        progress_cb=lambda *_: None,
    )

    assert result.cached is False
    assert target.read_bytes() == b"after"
    assert old.read_bytes() == b"old"
    assert calls[0]["overwrite"] is True
