"""
视频合集/合辑相关的接口 URL。
原 `src/archive.py` 中的合集接口迁移至此。
"""

from src.config.constants import API_BASE


class ArchiveUrls:
    """视频合集接口。"""

    # 获取合集内视频列表（seasons_archives_list，旧接口已失效，返回 -400，保留记录）
    SEASONS_ARCHIVES_LIST = f"{API_BASE}/x/polymer/web-space/seasons_archives_list"
    # 获取用户合集列表（seasons_series_list），返回的 seasons_list 每条已含完整 archives
    SEASONS_SERIES_LIST = f"{API_BASE}/x/polymer/web-space/seasons_series_list"
