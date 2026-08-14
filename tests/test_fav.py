"""收藏夹服务（FavService）的单元测试。"""

import pytest

from src.models import FavInfo
from src.services.fav import FavService


class TestResolveMediaId:
    def test_int(self):
        s = FavService()
        assert s._resolve_media_id(3953119978) == 3953119978

    def test_digit_string(self):
        assert FavService()._resolve_media_id("3953119978") == 3953119978

    def test_url_rejected(self):
        """后端只收规范值：URL 直接拒绝（解析在前端完成）。"""
        s = FavService()
        with pytest.raises(ValueError):
            s._resolve_media_id("https://space.bilibili.com/1/favlist?fid=42")

    def test_none_raises(self):
        s = FavService()
        with pytest.raises(ValueError):
            s._resolve_media_id(None)


class TestFavInfo:
    def test_from_dict(self):
        info = FavInfo.from_dict({"id": 1, "fid": 2, "mid": 3, "title": "我的收藏", "media_count": 10})
        assert info.title == "我的收藏"
        assert info.media_count == 10
        assert info.mid == 3

    def test_from_dict_empty(self):
        info = FavInfo.from_dict({})
        assert info.title == ""
        assert info.media_count == 0
