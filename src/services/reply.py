"""
评论服务：发表评论。
取代旧 `src/reply.py` 的 `BiliReply`，使用统一 BiliSession + 异常体系。
"""

import logging
from typing import Optional

from src.api.session import BiliSession
from src.config.cookie import BiliCookies
from src.urls.comment_urls import CommentUrls
from src.util.bvid import bv2av

logger = logging.getLogger(__name__)


class ReplyService:
    """B 站评论服务（暂时只支持视频评论）。"""

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    def send_reply(self, message: str, bvid: str = "", aid: int = 0) -> int:
        """发表评论。

        :param message: 评论内容
        :param bvid: 视频BV号（与 aid 二选一）
        :param aid: 视频av号（与 bvid 二选一）
        :return: 评论 rpid
        :raises BiliError: 评论失败（未登录/风控等）
        """
        if not bvid and not aid:
            raise ValueError("bvid 和 aid 不能同时为空")
        oid = bv2av(bvid) if bvid else aid
        csrf = BiliCookies.from_file().bili_jct or ""
        post_data = {
            "type": 1,
            "oid": oid,
            "message": message,
            "plat": 1,
            "csrf": csrf,  # CSRF Token是cookie中的bili_jct
        }
        data = self.session.post(
            CommentUrls.ADD,
            data=post_data,
            headers={"Referer": f"https://www.bilibili.com/video/{bvid}"} if bvid else None,
        )
        rpid = data.get("rpid", 0)
        logger.info("[ReplyService] 评论成功，rpid=%s", rpid)
        return rpid
