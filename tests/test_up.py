"""UP主空间视频服务（list_up_videos / download_up）的单元测试。"""

import pytest

from src.services import VideoService


class TestResolveMid:
    def test_int_mid(self):
        s = VideoService()
        assert s._resolve_mid(249056021) == 249056021

    def test_url_rejected(self):
        """后端只收规范值：空间 URL 直接拒绝（解析在前端完成）。"""
        s = VideoService()
        with pytest.raises(ValueError):
            s._resolve_mid("https://space.bilibili.com/249056021")
        with pytest.raises(ValueError):
            s._resolve_mid("https://space.bilibili.com/249056021/video")

    def test_invalid_url_raises(self):
        s = VideoService()
        with pytest.raises(ValueError):
            s._resolve_mid("https://example.com/123")

    def test_none_raises(self):
        s = VideoService()
        with pytest.raises(ValueError):
            s._resolve_mid(None)


class TestListUpVideos:
    def test_keeps_other_owners_but_logs_annotation(self, monkeypatch, caplog):
        """他人联合投稿仍返回（与空间页面一致），但要在日志里标注。"""
        import logging

        class FakeSession:
            def get(self, url, params=None):
                return {
                    "list": {"vlist": [
                        {"bvid": "BVown", "mid": 100, "author": "本UP"},
                        {"bvid": "BVguest", "mid": 200, "author": "别家"},
                    ]},
                    "page": {"count": 2},
                }

        import src.api.auth as auth_module
        monkeypatch.setattr(auth_module, "get_wbi", lambda params: None)

        service = VideoService(session=FakeSession())
        with caplog.at_level(logging.INFO):
            bvids = service.list_up_videos(100)

        assert bvids == ["BVown", "BVguest"]
        assert "2 条视频" in caplog.text
        assert "1 条为他人稿件" in caplog.text
        assert "BVguest" in caplog.text
        assert "BVown" not in caplog.text
