"""
收藏夹服务。
取代旧 `src/archive.py` 中的 `BiliFav`（原文件把收藏夹与合集混在一起，已拆分）。
"""

import logging
import re
from typing import Optional, Union

from src.api.session import BiliSession
from src.models.fav_model import FavInfo
from src.urls.fav_urls import FavUrls

logger = logging.getLogger(__name__)

# 收藏夹 URL 中的 fid 提取：如 https://space.bilibili.com/506925078/favlist?fid=3953119978&ftype=create
_FAV_URL_FID_RE = re.compile(r"[?&]fid=(\d+)")


class FavService:
    """B 站收藏夹服务。"""

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    @staticmethod
    def parse_fav_url(url: str) -> int:
        """从收藏夹页面 URL 解析 media_id（fid）。

        [使用方法]:
            FavService.parse_fav_url("https://space.bilibili.com/506925078/favlist?fid=3953119978&ftype=create")
            # 返回 3953119978

        :param url: 收藏夹页面 URL
        :return: media_id
        :raises ValueError: URL 中没有有效的 fid 参数
        """
        match = _FAV_URL_FID_RE.search(url)
        if not match:
            raise ValueError(f"收藏夹 URL 中未找到 fid 参数：{url}")
        return int(match.group(1))

    def _resolve_media_id(self, media_id: Optional[Union[int, str]]) -> int:
        """接受 media_id 或收藏夹 URL，统一返回 media_id。"""
        if media_id is None:
            raise ValueError("需要提供 media_id 或收藏夹 URL")
        s = str(media_id).strip()
        if s.startswith("http://") or s.startswith("https://"):
            return self.parse_fav_url(s)
        return int(s)

    def get_fav_info(self, media_id: Optional[Union[int, str]] = None) -> FavInfo:
        """获取收藏夹详情（名称/视频数量）。

        :param media_id: media_id 或收藏夹 URL
        :return: FavInfo
        """
        mid = self._resolve_media_id(media_id)
        data = self.session.get(FavUrls.FOLDER_INFO, params={"media_id": mid})
        return FavInfo.from_dict(data)

    def get_fav_bv(self, media_id: Optional[Union[int, str]] = None) -> list:
        """获取收藏夹内的视频 BV 号列表（一次性返回全部，不截断）。

        [使用方法]:
            service = FavService()
            bvs = service.get_fav_bv(3953119978)                      # 直接给 media_id
            bvs = service.get_fav_bv("https://space.bilibili.com/506925078/favlist?fid=3953119978")  # 或给 URL

        :param media_id: media_id 或收藏夹 URL
        :return: 视频bv号列表
        """
        mid = self._resolve_media_id(media_id)
        data = self.session.get(FavUrls.RESOURCE_IDS, params={"media_id": mid})
        return [fav["bvid"] for fav in data]
