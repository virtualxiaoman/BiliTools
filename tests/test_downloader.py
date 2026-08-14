"""下载工具（download_stream / merge_video_audio）的单元测试。"""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.api.errors import DownloadError, FFmpegNotFoundError
from src.util import downloader as dl


@pytest.fixture(autouse=True)
def reset_ffmpeg_cache():
    """每个用例前重置 ffmpeg 可用性缓存，避免污染。"""
    dl._ffmpeg_checked = False
    dl._ffmpeg_ok = False
    yield
    dl._ffmpeg_checked = False
    dl._ffmpeg_ok = False


def test_ffmpeg_available_cached():
    with patch("shutil.which", return_value="ffmpeg") as mock_which:
        assert dl.ffmpeg_available() is True
        assert dl.ffmpeg_available() is True
        assert mock_which.call_count == 1  # 只探测一次


def test_ffmpeg_not_available():
    with patch("shutil.which", return_value=None):
        assert dl.ffmpeg_available() is False


def test_merge_missing_ffmpeg():
    with patch("shutil.which", return_value=None):
        with pytest.raises(FFmpegNotFoundError):
            dl.merge_video_audio(Path("a"), Path("b"), Path("c"))


def test_merge_missing_input(tmp_path):
    """输入文件不存在时应直接报错，不启动 ffmpeg。"""
    with patch("shutil.which", return_value="ffmpeg"), patch("subprocess.run") as mock_run:
        with pytest.raises(DownloadError):
            dl.merge_video_audio(tmp_path / "no.mp4", tmp_path / "no.m4a", tmp_path / "out.mp4")
        mock_run.assert_not_called()


def test_merge_command_has_yes_flag(tmp_path):
    """ffmpeg 命令必须带 -y，否则目标已存在时会挂起。"""
    video = tmp_path / "v.mp4"
    audio = tmp_path / "a.m4a"
    video.write_bytes(b"v")
    audio.write_bytes(b"a")
    with patch("shutil.which", return_value="ffmpeg"), patch(
        "subprocess.run",
        return_value=__import__("subprocess").CompletedProcess(args=[], returncode=0),
    ) as mock_run:
        dl.merge_video_audio(video, audio, tmp_path / "out.mp4")
        cmd = mock_run.call_args[0][0]
        assert "-y" in cmd
        assert "-i" in cmd


def test_merge_ffmpeg_failure(tmp_path):
    video = tmp_path / "v.mp4"
    audio = tmp_path / "a.m4a"
    video.write_bytes(b"v")
    audio.write_bytes(b"a")
    failed = __import__("subprocess").CompletedProcess(args=[], returncode=1,
                                                       stderr=b"bad input")
    with patch("shutil.which", return_value="ffmpeg"), patch("subprocess.run", return_value=failed):
        with pytest.raises(DownloadError):
            dl.merge_video_audio(video, audio, tmp_path / "out.mp4")


def test_download_stream_writes_file(tmp_path):
    """download_stream 应流式写入并返回字节数。"""
    class FakeResp:
        headers = {"Content-Length": "11"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            yield b"hello "; yield b"world"

    with patch("requests.get", return_value=FakeResp()):
        target = tmp_path / "f.bin"
        size = dl.download_stream("http://x", target)
        assert size == 11
        assert target.read_bytes() == b"hello world"


def test_download_stream_progress(tmp_path):
    """进度回调应被逐块调用。"""
    class FakeResp:
        headers = {"Content-Length": "10"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            yield b"12345"; yield b"67890"

    calls = []
    with patch("requests.get", return_value=FakeResp()):
        dl.download_stream("http://x", tmp_path / "f.bin", progress_cb=lambda d, t: calls.append((d, t)))
    assert calls == [(5, 10), (10, 10)]


def test_download_stream_request_failure(tmp_path):
    class BadResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self):
            raise __import__("requests").HTTPError("404")

    with patch("requests.get", return_value=BadResp()):
        with pytest.raises(DownloadError):
            dl.download_stream("http://x", tmp_path / "f.bin")


def test_download_stream_resume_after_interrupt(tmp_path):
    """网络中断后应从已下载位置断点续传，最终得到完整文件。"""
    import requests

    FULL = b"hello world"

    class FakeResp:
        def __init__(self, body, status_code=200):
            self._body = body
            self.status_code = status_code
            self.headers = {"Content-Length": str(len(body))}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            yield self._body

    def fake_get(url, headers=None, stream=False, timeout=None):
        rng = (headers or {}).get("Range", "")
        if rng:
            # 断点续传：服务器返回 206 + 剩余部分
            start = int(rng.split("=")[1].split("-")[0])
            return FakeResp(FULL[start:], status_code=206)
        # 首次：读到一半抛 IncompleteRead，模拟断流
        resp = FakeResp(FULL, status_code=200)
        def _iter(chunk_size):
            yield FULL[:5]
            raise requests.exceptions.ConnectionError(
                "IncompleteRead(5 bytes read, 6 more expected)"
            )
        resp.iter_content = _iter
        return resp

    with patch("requests.get", side_effect=fake_get) as mock_get:
        target = tmp_path / "f.bin"
        size = dl.download_stream("http://x", target, max_retries=2)
        assert size == 11
        assert target.read_bytes() == FULL
        assert mock_get.call_count == 2  # 首次 + 1 次续传
        # 第二次请求带 Range 头
        assert mock_get.call_args_list[1].kwargs["headers"]["Range"] == "bytes=5-"


def test_download_stream_resume_ignored_range_restarts(tmp_path):
    """服务器忽略 Range（续传时返回 200 全量）应丢弃半截文件从头下载，不追加损坏。"""
    import requests

    FULL = b"hello world"

    class FakeResp:
        def __init__(self, body, status_code=200):
            self._body = body
            self.status_code = status_code
            self.headers = {"Content-Length": str(len(body))}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            yield self._body

    def fake_get(url, headers=None, stream=False, timeout=None):
        rng = (headers or {}).get("Range", "")
        if rng:
            # 服务器忽略 Range：仍返回 200 全量内容
            return FakeResp(FULL, status_code=200)
        # 首次：读到一半抛 IncompleteRead，留下 5 字节半截文件
        resp = FakeResp(FULL, status_code=200)
        def _iter(chunk_size):
            yield FULL[:5]
            raise requests.exceptions.ConnectionError("IncompleteRead")
        resp.iter_content = _iter
        return resp

    with patch("requests.get", side_effect=fake_get) as mock_get:
        target = tmp_path / "f.bin"
        size = dl.download_stream("http://x", target, max_retries=2)
        assert size == 11
        # 最终文件完整（若按追加写入会变成 5+11=16 字节的损坏文件）
        assert target.read_bytes() == FULL
        assert mock_get.call_count == 2
        assert mock_get.call_args_list[1].kwargs["headers"]["Range"] == "bytes=5-"


def test_download_stream_gives_up_after_retries(tmp_path):
    """连续失败达到重试上限后应抛 DownloadError。"""
    import requests

    class BadResp:
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, chunk_size):
            raise requests.exceptions.ConnectionError("broken")

    with patch("requests.get", return_value=BadResp()):
        with pytest.raises(DownloadError):
            dl.download_stream("http://x", tmp_path / "f.bin", max_retries=2)
