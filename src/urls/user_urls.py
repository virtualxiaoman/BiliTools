"""
用户（UP主/空间）相关的接口 URL。
原 `src/up.py`、`src/video.py` 中的用户信息接口迁移至此。
"""

from src.config.constants import API_BASE, SPACE_BASE


class UserUrls:
    """用户空间信息、粉丝、关注等接口。"""

    # 固定端点（无路径参数）
    ACC_INFO = f"{API_BASE}/x/space/acc/info"  # 用户公开信息（昵称/头像等）
    ACC_INFO_WBI = f"{API_BASE}/x/space/wbi/acc/info"  # 用户信息（需 wbi 签名 + 风控参数）
    CARD = f"{API_BASE}/x/web-interface/card"  # 用户卡片信息（粉丝数等）
    SPACE_ARC_SEARCH = f"{API_BASE}/x/space/wbi/arc/search"  # 用户空间视频列表（需 wbi 签名）

    @staticmethod
    def space_home(mid: int) -> str:
        """用户空间主页。"""
        return f"{SPACE_BASE}/{mid}/"

    @staticmethod
    def favlist(mid: int) -> str:
        """用户收藏夹页面。"""
        return f"{SPACE_BASE}/{mid}/favlist"
