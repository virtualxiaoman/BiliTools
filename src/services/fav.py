"""
收藏夹服务。
取代旧 `src/archive.py` 中的 `BiliFav`（原文件把收藏夹与合集混在一起，已拆分）。
"""

import logging
from typing import Optional

from src.api.session import BiliSession
from src.urls.fav_urls import FavUrls

logger = logging.getLogger(__name__)


class FavService:
    """B 站收藏夹服务。"""

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    def get_fav_bv(self, media_id: int) -> list:
        """获取收藏夹内的视频 BV 号列表。

        :param media_id: 收藏夹 media_id
        :return: 视频bv号列表
        """
        data = self.session.get(FavUrls.RESOURCE_IDS, params={"media_id": media_id})
        return [fav["bvid"] for fav in data]
