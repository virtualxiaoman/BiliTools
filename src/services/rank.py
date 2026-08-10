"""
排行榜/热门服务。
取代旧 `src/rank.py` 的 `BiliRank`。
"""

import logging
from typing import Optional

from src.api.session import BiliSession
from src.urls.rank import RankUrls

logger = logging.getLogger(__name__)


class RankService:
    """B 站排行榜/热门服务。"""

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    def get_popular(self, pn: int = 1, ps: int = 20) -> list:
        """获取综合热门视频列表：https://www.bilibili.com/v/popular/all

        [使用方法]:
            bvs = RankService().get_popular()
        [注意]可以使用下面的方法获取热门视频列表：
            bvs = []
            for i in range(1, 6):
                bvs.extend(RankService().get_popular(pn=i))

        :param pn: 页码
        :param ps: 每页项数
        :return: 视频的bv号列表
        """
        data = self.session.get(RankUrls.POPULAR, params={"pn": pn, "ps": ps})
        return [video["bvid"] for video in data.get("list", [])]

    def get_ranking(self, tid: Optional[int] = None) -> list:
        """获取排行榜视频列表：https://www.bilibili.com/v/popular/rank/all

        :param tid: [有问题]分区id，但似乎不起作用。文档: https://socialsisteryi.github.io/bilibili-API-collect/docs/video/video_zone.html
        :return: 视频的bv号列表
        """
        params = {"tid": tid} if tid is not None else None
        data = self.session.get(RankUrls.RANKING, params=params)
        return [video["bvid"] for video in data.get("list", [])]

    def get_new(self, rid: int = 1, pn: int = 1, ps: int = 5) -> list:
        """[有问题]获取新视频列表，但似乎不是最新的，目前不知道是干什么的

        :param rid: [必要]目标分区tid
        :param pn: 页码
        :param ps: 每页项数
        :return: 视频的bv号列表
        """
        params = {"rid": rid, "pn": pn, "ps": ps}
        data = self.session.get(RankUrls.NEW, params=params)
        return [video["bvid"] for video in data.get("archives", [])]
