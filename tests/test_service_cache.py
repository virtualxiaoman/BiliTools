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
