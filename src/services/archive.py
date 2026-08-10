"""
视频合集服务。
取代旧 `src/archive.py` 中的 `BiliArchive`（原文件把收藏夹与合集混在一起，已拆分）。

说明：`seasons_archives_list` 接口需要完整的 `page_num`/`page_size` 参数，
缺任一参数会返回 -400（旧代码因此误判为接口失效）。
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

        [注意] 此接口仅能查询**任意用户**的合集列表（不需登录身份），
        但返回的每条合集结构较简略（meta + archives 视频列表，无分P信息）。

        :param mid: 用户UID
        :param page_num: 页码
        :param page_size: 每页数量
        :return: 合集列表，每条含 meta(season_id/name) 与 archives(视频列表)
        """
        params = {"mid": mid, "page_num": page_num, "page_size": page_size}
        data = self.session.get(ArchiveUrls.SEASONS_SERIES_LIST, params=params)
        return data.get("items_lists", {}).get("seasons_list", [])

    def get_season_by_id(self, season_id: int, mid: int = 0) -> dict:
        """按 season_id 获取合集详情（meta + 完整视频列表）。

        [注意] 该接口需要完整的 page_num/page_size 参数，缺任一返回 -400。
        mid 不要求是登录用户（任意 UP 主的合集都能查），但传入 mid 能帮助定位。

        :param season_id: 合集 sid
        :param mid: 合集所属用户UID。为 0 时尝试使用当前登录用户 mid
        :return: dict，含 meta(合集信息) 与 archives(视频列表)
        :raises ValueError: 合集不存在或无法解析
        """
        if not mid:
            from src.services.login import LoginService
            mid = LoginService(self.session).get_mid() or 0
        params = {"mid": mid, "season_id": season_id, "page_num": 1, "page_size": 50}
        data = self.session.get(ArchiveUrls.SEASONS_ARCHIVES_LIST, params=params)
        if not data or not data.get("archives"):
            raise ValueError(f"合集 {season_id} 不存在或没有视频。")
        return data

    def get_archives_list(self, season_id: int, mid: int = 0) -> list:
        """获取指定合集内视频的 BV 号列表。

        [使用方法]:
            service = ArchiveService()
            # 和纱猫猫小剧场, url: https://space.bilibili.com/37507923/channel/collectiondetail?sid=2033914
            bvids = service.get_archives_list(2033914)
            print(bvids)

        :param season_id: 合集 sid
        :param mid: 合集所属用户UID。0 时尝试用当前登录用户 mid
        :return: 视频bv号列表
        """
        data = self.get_season_by_id(season_id, mid)
        return [a["bvid"] for a in data.get("archives", [])]
