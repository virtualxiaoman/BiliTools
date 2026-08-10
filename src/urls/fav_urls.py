"""
收藏夹相关的接口 URL。
原 `src/archive.py` 中的收藏夹接口迁移至此。
"""

from src.config.constants import API_BASE


class FavUrls:
    """收藏夹接口。"""

    RESOURCE_IDS = f"{API_BASE}/x/v3/fav/resource/ids"  # 获取收藏夹内视频（by media_id）
