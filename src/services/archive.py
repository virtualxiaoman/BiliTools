"""
视频合集服务。
取代旧 `src/archive.py` 中的 `BiliArchive`（原文件把收藏夹与合集混在一起，已拆分）。

说明：旧代码使用的 `seasons_archives_list` 接口已失效（一律返回 -400），
改为使用同系列的 `seasons_series_list` 接口获取合集列表（每条合集已含完整视频列表）。
"""

import logging
from typing import Optional

from src.api.session import BiliSession
from src.urls.archive import ArchiveUrls

logger = logging.getLogger(__name__)


class ArchiveService:
    """B 站视频合集服务。"""

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    def list_seasons(self, mid: int, page_num: int = 1, page_size: int = 10) -> list:
        """获取用户的全部合集（seasons_list）。

        :param mid: 用户UID
        :param page_num: 页码
        :param page_size: 每页数量
        :return: 合集列表，每条含 meta(season_id/name) 与 archives(视频列表)
        """
        params = {"mid": mid, "page_num": page_num, "page_size": page_size}
        data = self.session.get(ArchiveUrls.SEASONS_SERIES_LIST, params=params)
        return data.get("items_lists", {}).get("seasons_list", [])

    def get_archives_list(self, season_id: int, mid: int = 0) -> list:
        """获取指定合集内视频的 BV 号列表。

        [使用方法]:
            service = ArchiveService()
            # 和纱猫猫小剧场, url: https://space.bilibili.com/37507923/channel/collectiondetail?sid=2033914
            bvids = service.get_archives_list(2033914)
            print(bvids)

        :param season_id: 合集 sid
        :param mid: 合集所属用户UID。传入 0 时会在用户的合集中查找该 season_id
        :return: 视频bv号列表
        """
        if mid:
            seasons = self.list_seasons(mid)
            for season in seasons:
                meta = season.get("meta") or {}
                if meta.get("season_id") == season_id:
                    return [a["bvid"] for a in season.get("archives", [])]
            logger.warning("[ArchiveService] 用户 %s 未找到合集 %s", mid, season_id)
            return []
        # 未指定 mid：遍历若干页用户合集（依赖默认登录用户）
        from src.services.login import LoginService

        mid = LoginService(self.session).get_mid() or 0
        if not mid:
            raise ValueError("无法确定合集所属用户 mid，请传入 mid 参数")
        return self.get_archives_list(season_id, mid=mid)
