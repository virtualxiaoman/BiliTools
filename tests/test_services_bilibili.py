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
TEST_MULTI_PAGE_BVID = "BV1Q43w6QETb"  # 多P视频（9P），属于合集「洛天依·纯蓝幻乐」


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
    bvs = ArchiveService().get_bvlist_by_sid(TEST_SEASON_ID, mid=0)
    assert len(bvs) > 0


def test_fetch_season_by_sid(video_service: VideoService):
    """按 sid 获取合集结构（不依赖 bvid）。"""
    season = video_service.fetch_season(season_id=8683221)  # 洛天依·纯蓝幻乐
    assert season is not None
    assert season.title
    assert len(season.episodes) >= 1
    # episodes 应补全分P信息
    ep = season.episodes[0]
    assert ep.bvid
    assert len(ep.pages) >= 1


def test_fetch_season_by_sid_other(video_service: VideoService):
    """按 sid 获取他人合集。"""
    season = video_service.fetch_season(season_id=1717000, mid=506925078)  # 明日方舟
    assert season is not None
    assert len(season.episodes) > 1


def test_fetch_season_multi_page(video_service: VideoService):
    """多P视频应解析出全部分P + 所属合集。"""
    info = video_service.fetch_info(TEST_MULTI_PAGE_BVID)
    assert info.is_multi_page is True
    assert len(info.pages) > 1
    assert info.season is not None
    assert info.season.title
    assert len(info.season.episodes) >= 1


def test_download_multi_page_audio(tmp_path, video_service: VideoService):
    """多P视频指定分P下载音频，文件名应含 P 序号。"""
    result = video_service.download_audio(TEST_MULTI_PAGE_BVID, tmp_path, page=2)
    assert result.path.exists()
    assert "-P02-" in result.path.name


def test_fav_get_bv():
    """收藏夹 bvid 列表（传 media_id）。"""
    from src.services import FavService
    fav = FavService()
    bvs = fav.get_fav_bv(3953119978)
    assert len(bvs) >= 1
    assert all(b.startswith("BV") for b in bvs)


def test_fav_get_info():
    from src.services import FavService
    info = FavService().get_fav_info(3953119978)
    assert info.title
    assert info.media_count >= 1


def test_download_fav_first_audio(tmp_path, video_service: VideoService):
    """收藏夹下载：仅取第一个视频的音频验证链路（避免下载整个收藏夹）。"""
    from src.services import FavService
    fav = FavService()
    bvs = fav.get_fav_bv(3953119978)
    assert bvs, "收藏夹为空"
    result = video_service.download_audio(bvs[0], tmp_path)
    assert result.path.exists()
    assert result.size > 0


TEST_UP_MID_SPACE = 249056021  # 星末绫初，3 个短视频


def test_list_up_videos(video_service: VideoService):
    """获取 UP 主全部视频 bvid。"""
    bvs = video_service.list_up_videos(TEST_UP_MID_SPACE)
    assert len(bvs) >= 1
    assert all(b.startswith("BV") for b in bvs)


def test_download_up_first_audio(tmp_path, video_service: VideoService):
    """UP主下载：仅取第一个视频的音频验证链路。"""
    bvs = video_service.list_up_videos(TEST_UP_MID_SPACE)
    assert bvs
    result = video_service.download_audio(bvs[0], tmp_path)
    assert result.path.exists()
    assert result.size > 0
