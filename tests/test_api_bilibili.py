"""真实网络集成测试（标记 @pytest.mark.network，默认跳过）。

运行方式：
    pytest tests/test_api_bilibili.py --network      # 只跑这个文件的网络测试
    pytest tests/ --network                          # 跑全部网络测试

[注意] 需要能够访问 B 站（可能需要科学上网），且默认 cookie 已登录。
"""

import pytest

from src.api import BiliSession
from src.api.auth import get_wbi
from src.urls import LoginUrls, RankUrls, VideoUrls

pytestmark = pytest.mark.network

# 测试用视频：动画小剧场《补习部的一天》第4集：烟火（up主：蔚蓝档案）
TEST_BVID = "BV1ov42117yC"
TEST_UP_MID = 3493265644980448  # 蔚蓝档案官方


def test_session_fetch_video_view(session: BiliSession):
    data = session.get(VideoUrls.VIEW, params={"bvid": TEST_BVID})
    assert data["bvid"] == TEST_BVID
    assert data["title"]
    assert data["stat"]["view"] > 0


def test_session_login_state(session: BiliSession):
    data = session.get(LoginUrls.LOGIN_STATE)
    assert "mid" in data or "isLogin" in data


def test_session_error_on_invalid_bv(session: BiliSession):
    from src.api.errors import BiliAPIError
    with pytest.raises(BiliAPIError):
        session.get(VideoUrls.VIEW, params={"bvid": "BV1inValidXX"})


def test_wbi_signature_real():
    wts, w_rid = get_wbi({"bvid": TEST_BVID})
    assert isinstance(wts, int)
    assert len(w_rid) == 32


def test_rank_popular(session: BiliSession):
    data = session.get(RankUrls.POPULAR, params={"pn": 1, "ps": 5})
    assert len(data["list"]) == 5
    assert all(v["bvid"].startswith("BV") for v in data["list"])
