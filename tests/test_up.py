"""UP主空间视频服务（list_up_videos / download_up）的单元测试。"""

import pytest

from src.services import VideoService


class TestResolveMid:
    def test_int_mid(self):
        s = VideoService()
        assert s._resolve_mid(249056021) == 249056021

    def test_space_url(self):
        s = VideoService()
        assert s._resolve_mid("https://space.bilibili.com/249056021") == 249056021

    def test_space_url_with_path(self):
        s = VideoService()
        assert s._resolve_mid("https://space.bilibili.com/249056021/video") == 249056021

    def test_invalid_url_raises(self):
        s = VideoService()
        with pytest.raises(ValueError):
            s._resolve_mid("https://example.com/123")

    def test_none_raises(self):
        s = VideoService()
        with pytest.raises(ValueError):
            s._resolve_mid(None)
