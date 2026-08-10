"""
排行榜/热门相关的接口 URL。
原 `src/rank.py` 中的排行榜接口迁移至此。
"""

from src.config.constants import API_BASE


class RankUrls:
    """综合热门与排行榜接口。"""

    POPULAR = f"{API_BASE}/x/web-interface/popular"  # 综合热门视频列表
    RANKING = f"{API_BASE}/x/web-interface/ranking/v2"  # 排行榜视频列表
    NEW = f"{API_BASE}/x/web-interface/dynamic/region"  # 分区最新视频
