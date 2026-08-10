"""
收藏夹相关的接口 URL。
原 `src/archive.py` 中的收藏夹接口迁移至此。
"""

from src.config.constants import API_BASE, SPACE_BASE


class FavUrls:
    """收藏夹接口。"""

    RESOURCE_IDS = f"{API_BASE}/x/v3/fav/resource/ids"  # 获取收藏夹内视频（by media_id，一次性返回全部 id）
    FOLDER_INFO = f"{API_BASE}/x/v3/fav/folder/info"  # 收藏夹详情（名称/数量）

    @staticmethod
    def fav_page(uid: int, fid: int) -> str:
        """用户收藏夹页面 URL（如 https://space.bilibili.com/506925078/favlist?fid=3953119978）。"""
        return f"{SPACE_BASE}/{uid}/favlist?fid={fid}&ftype=create"
