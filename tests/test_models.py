"""数据模型（dataclass）的单元测试。"""

from src.models import LoginUser, VideoInfo, VideoOwner, VideoStat
from src.models.download import DashStreams, VideoQuality, VideoStream
from src.models.history import HistoryItem, HistoryPage


class TestVideoStat:
    def test_from_dict(self):
        stat = VideoStat.from_dict({"view": 100, "danmaku": 5, "reply": 2, "like": 10,
                                    "coin": 1, "favorite": 3, "share": 4})
        assert stat.num_view == 100
        assert stat.num_dm == 5
        assert stat.num_reply == 2
        assert stat.num_fav == 3

    def test_from_dict_defaults(self):
        stat = VideoStat.from_dict({})
        assert stat.num_view == 0
        assert stat.num_dm == 0


class TestVideoInfo:
    def test_from_view_json(self):
        data = {
            "bvid": "BV1ov42117yC", "aid": 123,
            "title": "标题", "pic": "http://p.jpg", "desc": "简介",
            "pubdate": 1700000000, "tid": 4, "tname": "游戏",
            "stat": {"view": 100, "danmaku": 5},
            "owner": {"mid": 99, "name": "up主"},
            "pages": [{"cid": 777}],
        }
        info = VideoInfo.from_view_json(data)
        assert info.bvid == "BV1ov42117yC"
        assert info.cid == 777
        assert info.owner.name == "up主"
        assert info.stat.num_view == 100

    def test_from_view_json_no_pages(self):
        info = VideoInfo.from_view_json({"bvid": "BV1xx411c7mD"})
        assert info.cid is None


class TestDownloadModels:
    def test_quality_enum(self):
        # 对齐 BAC 文档的 qn 值定义
        assert VideoQuality.P360 == 16
        assert VideoQuality.P480 == 32
        assert VideoQuality.P720 == 64
        assert VideoQuality.P1080 == 80
        assert VideoQuality.P1080_PLUS == 112
        assert VideoQuality.HD4K == 120
        assert VideoQuality.HDR == 125
        assert VideoQuality.DOLBY == 126
        assert VideoQuality.HD8K == 127

    def test_quality_enum_ordering(self):
        """枚举值应按清晰度升序排列（用于排序比较）。"""
        values = [q.value for q in VideoQuality]
        assert values == sorted(values)

    def test_video_stream_ext(self):
        assert VideoStream(url="http://x/1.mp4").ext == "mp4"
        assert VideoStream(url="http://x/1.flv").ext == "flv"
        assert VideoStream(url="http://x/1", codecs="avc1").ext == "m4s"
        assert VideoStream(url="http://x/1", codecs="hev1").ext == "m4s"
        assert VideoStream(url="http://x/1", codecs="av01").ext == "m4s"

    def test_audio_stream_ext(self):
        assert DashStreams().best_audio() is None

    def test_dash_pick_video(self):
        dash = DashStreams(video=[
            VideoStream(url="a", quality=16),  # 360P
            VideoStream(url="b", quality=64),  # 720P
            VideoStream(url="c", quality=80),  # 1080P
        ])
        assert dash.best_video().url == "c"
        # 要求 720P：应命中 1080P（不低于目标的第一档）
        assert dash.pick_video(VideoQuality.P720).url == "c"
        # 要求 1080P：精确命中
        assert dash.pick_video(VideoQuality.P1080).url == "c"
        # 要求 4K（无此档）：回退到最高
        assert dash.pick_video(VideoQuality.HD4K).url == "c"
        # 空流
        assert DashStreams().pick_video(VideoQuality.P1080) is None


class TestHistoryModels:
    def test_view_percent(self):
        assert HistoryItem(progress=50, duration=100).view_percent == "50.00%"
        assert HistoryItem(progress=-1).view_percent == "100.00%"
        assert HistoryItem(progress=10, duration=0).view_percent == "-1.00%"

    def test_history_page_from_json(self):
        data = {
            "list": [
                {"history": {"oid": 1, "business": "archive", "bvid": "BV1xx411c7mD"},
                 "progress": 30, "duration": 60, "view_at": 123},
                {"history": {"oid": 2, "business": "pgc"}, "view_at": 124},
            ],
            "cursor": {"has_more": True, "max": 999, "business": "archive", "view_at": 123},
        }
        page = HistoryPage.from_json(data)
        assert len(page.items) == 2
        assert page.has_more is True
        assert page.max == 999
        arch = page.items[0]
        assert arch.bvid == "BV1xx411c7mD"
        assert arch.view_percent == "50.00%"


class TestLoginUser:
    def test_from_nav_json(self):
        user = LoginUser.from_nav_json({"isLogin": True, "mid": 1, "uname": "u",
                                        "face": "f", "level_info": {"current_level": 5}})
        assert user.is_login and user.mid == 1 and user.uname == "u" and user.level == 5

    def test_from_nav_json_not_login(self):
        user = LoginUser.from_nav_json({"isLogin": False})
        assert user.is_login is False
        assert user.mid is None
