"""services 层真实网络集成测试（标记 @pytest.mark.network，默认跳过）。

覆盖：视频信息/下载、登录态、用户信息、排行、历史、收藏、合集。

[注意] 需要可访问 B 站且默认 cookie 已登录。
下载测试使用最小清晰度（P360），避免下载大文件。
"""

import pytest

from src.models import VideoQuality
from src.services import (
    ArchiveService,
    FavService,
    HistoryService,
    LoginService,
    RankService,
    UserService,
    VideoService,
)

pytestmark = pytest.mark.network

TEST_BVID = "BV1ov42117yC"  # 动画小剧场《补习部的一天》第4集：烟火
TEST_UP_MID = 3493265644980448  # 蔚蓝档案官方
TEST_FAV_MEDIA_ID = 827560778  # 用户自己的默认收藏夹（需登录）
TEST_SEASON_ID = 1717000  # 合集·明日方舟（属当前登录用户）


def test_fetch_info(video_service: VideoService):
    info = video_service.fetch_info(TEST_BVID)
    assert info.bvid == TEST_BVID
    assert info.title
    assert info.cid is not None
    assert info.owner.name
    assert info.stat.num_view > 0


def test_fetch_info_with_tags(video_service: VideoService):
    info = video_service.fetch_info_with_tags(TEST_BVID)
    assert info.tags  # 至少一个标签


def test_get_playurl(video_service: VideoService):
    info = video_service.fetch_info(TEST_BVID)
    dash = video_service.get_playurl(TEST_BVID, info.cid)
    assert dash.best_video() is not None
    assert dash.best_audio() is not None


def test_download_cover(tmp_path, video_service: VideoService):
    result = video_service.download_cover(TEST_BVID, tmp_path)
    assert result.path.exists()
    assert result.size and result.size > 0
    assert result.path.suffix in (".jpg", ".png")


def test_download_audio(tmp_path, video_service: VideoService):
    result = video_service.download_audio(TEST_BVID, tmp_path)
    assert result.path.exists()
    assert result.size and result.size > 100_000


def test_download_video_only(tmp_path, video_service: VideoService):
    result = video_service.download_video(TEST_BVID, tmp_path, quality=VideoQuality.P360)
    assert result.path.exists()
    assert result.size and result.size > 100_000


def test_download_video_with_audio(tmp_path, video_service: VideoService):
    result = video_service.download_video_with_audio(
        TEST_BVID, tmp_path, quality=VideoQuality.P360
    )
    assert result.path.exists()
    assert result.path.suffix == ".mp4"
    assert result.size and result.size > 1_000_000


def test_login_state(video_service):
    from src.services import LoginService
    user = LoginService().get_login_state()
    assert user.is_login is True  # 需要已登录


def test_user_info():
    info = UserService().fetch_info(TEST_UP_MID)
    assert info.name
    assert info.num_follower > 0


def test_rank_popular():
    bvs = RankService().get_popular(pn=1, ps=3)
    assert len(bvs) == 3
    assert all(b.startswith("BV") for b in bvs)


def test_history_page():
    page = HistoryService().get_history_page(ps=3)
    assert len(page.items) > 0


def test_fav_bv():
    bvs = FavService().get_fav_bv(TEST_FAV_MEDIA_ID)
    assert len(bvs) > 0


def test_archive_list():
    # 合集「明日方舟」属于当前登录用户，mid=0 时自动解析为登录用户 mid
    bvs = ArchiveService().get_archives_list(TEST_SEASON_ID, mid=0)
    assert len(bvs) > 0
