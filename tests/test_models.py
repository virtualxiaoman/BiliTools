"""数据模型（dataclass）的单元测试。"""

import pytest

from src.models import LoginUser, VideoInfo, VideoOwner, VideoSeason, VideoStat
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
        assert info.pages == []
        assert info.is_multi_page is False
        assert info.season is None


class TestMultiPageAndSeason:
    def test_from_view_json_multi_page(self):
        data = {
            "bvid": "BV1Q43w6QETb", "aid": 1,
            "title": "多P视频",
            "pages": [
                {"page": 1, "cid": 111, "part": "第一P", "duration": 100,
                 "dimension": {"width": 1920, "height": 1080}},
                {"page": 2, "cid": 222, "part": "第二P", "duration": 200,
                 "dimension": {"width": 1920, "height": 1080}},
            ],
            "ugc_season": {
                "id": 8683221, "title": "测试合集", "mid": 506925078, "ep_count": 1,
                "sections": [{"title": "正片", "episodes": [
                    {"bvid": "BV1Q43w6QETb", "aid": 1, "title": "多P视频", "pages": [
                        {"page": 1, "cid": 111, "part": "第一P", "duration": 100},
                        {"page": 2, "cid": 222, "part": "第二P", "duration": 200},
                    ]},
                ]}],
            },
        }
        info = VideoInfo.from_view_json(data)
        assert info.is_multi_page is True
        assert len(info.pages) == 2
        assert info.pages[0].cid == 111
        assert info.pages[1].part == "第二P"
        assert info.season.id == 8683221
        assert info.season.title == "测试合集"
        assert len(info.season.episodes) == 1
        ep = info.season.episodes[0]
        assert ep.bvid == "BV1Q43w6QETb"
        assert ep.is_multi_page is True

    def test_season_no_episodes(self):
        season = VideoSeason.from_dict({"id": 1, "title": "空合集", "sections": []})
        assert season.episodes == []
        assert season.ep_count == 0


class TestFetchSeason:
    """VideoService.fetch_season 的 bvid/sid 双通道逻辑（mock ArchiveService）。"""

    def test_season_id_requires_param(self):
        from src.services import VideoService
        s = VideoService()
        with pytest.raises(ValueError):
            s.fetch_season()  # 两个参数都没有

    def test_season_id_builds_episodes(self):
        from unittest.mock import MagicMock, patch
        from src.services import VideoService
        from src.models import VideoInfo, VideoPage

        s = VideoService()
        fake_arch_service = MagicMock()
        fake_arch_service.get_season_by_id.return_value = {
            "meta": {"season_id": 8683221, "title": "洛天依·纯蓝幻乐", "mid": 1, "total": 2},
            "archives": [{"bvid": "BV1A", "aid": 1, "title": "稿件A"}, {"bvid": "BV1B", "aid": 2, "title": "稿件B"}],
        }

        def fake_fetch_info(bvid):
            return VideoInfo(bvid=bvid, pages=[VideoPage(page=1, cid=1, part="唯一")])

        with patch("src.services.video.ArchiveService", return_value=fake_arch_service):
            s.fetch_info = fake_fetch_info
            season = s.fetch_season(season_id=8683221)

        assert season is not None
        assert season.title == "洛天依·纯蓝幻乐"
        assert len(season.episodes) == 2
        assert season.episodes[0].bvid == "BV1A"
        assert season.episodes[0].pages[0].cid == 1  # fetch_info 补全分P


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

    def test_quality_display_name(self):
        assert VideoQuality.HD4K.display_name == "4K"
        assert VideoQuality.P1080.display_name == "1080P"
        assert VideoQuality.HDR.display_name == "HDR"
        assert VideoQuality.DOLBY.display_name == "杜比"

    def test_quality_from_qn(self):
        assert VideoQuality.from_qn(120) == VideoQuality.HD4K
        assert VideoQuality.from_qn(80) == VideoQuality.P1080
        assert VideoQuality.from_qn(999) is None

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
        # 精确目标：要求 1080P → 命中 1080P
        assert dash.pick_video(VideoQuality.P1080).url == "c"
        # 要求 720P → 命中 720P（不再上取更高）
        assert dash.pick_video(VideoQuality.P720).url == "b"
        # 要求 360P → 命中 360P
        assert dash.pick_video(VideoQuality.P360).url == "a"
        # 视频没有 4K 流 → 回退到最高可用
        assert dash.pick_video(VideoQuality.HD4K).url == "c"
        # 空流
        assert DashStreams().pick_video(VideoQuality.P1080) is None

    def test_pick_video_precise_target_not_higher(self):
        """关键语义：视频有 4K(120) 与 1080P(80)，要求 1080P 必须取 1080P 而非 4K。"""
        dash = DashStreams(video=[
            VideoStream(url="4k", quality=120),
            VideoStream(url="1080", quality=80),
            VideoStream(url="720", quality=64),
        ])
        assert dash.pick_video(VideoQuality.P1080).url == "1080"  # 不被拉到 4K
        assert dash.pick_video(VideoQuality.HD4K).url == "4k"      # 默认(HD4K)取最高
        assert dash.pick_video(VideoQuality.P720).url == "720"


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


class TestUnifiedDownload:
    """VideoService.download(bvid) 统一下载接口的分流逻辑。"""

    def test_dispatch_to_season_or_pages(self):
        from unittest.mock import patch
        from src.services import VideoService
        from src.models import VideoInfo, VideoPage, VideoSeason, VideoSeasonEpisode

        s = VideoService()
        info_in_season = VideoInfo(
            bvid="BV1A",
            season=VideoSeason(id=1, title="A", episodes=[VideoSeasonEpisode(bvid="BV1A")]),
        )
        info_single = VideoInfo(bvid="BV1B", pages=[VideoPage(page=1, cid=1)], season=None)

        with patch.object(s, "fetch_info", side_effect=[info_in_season, info_single]), \
             patch.object(s, "download_season", return_value=["r1"]) as m_season, \
             patch.object(s, "download_all_pages", return_value=["r2"]) as m_pages:
            assert s.download("BV1A") == ["r1"]
            assert m_season.call_count == 1
            assert s.download("BV1B") == ["r2"]
            assert m_pages.call_count == 1
            # 默认使用最高清晰度 HD4K
            from src.models import VideoQuality
            assert m_season.call_args.kwargs["quality"] == VideoQuality.HD4K
            assert m_pages.call_args.kwargs["quality"] == VideoQuality.HD4K
