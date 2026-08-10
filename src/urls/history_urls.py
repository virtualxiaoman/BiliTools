"""
历史记录相关的接口 URL。
原 `src/history.py` 中的历史记录接口迁移至此。
"""

from src.config.constants import API_BASE


class HistoryUrls:
    """历史记录（观看记录）接口。"""

    CURSOR = f"{API_BASE}/x/web-interface/history/cursor"  # 历史记录（游标分页）
