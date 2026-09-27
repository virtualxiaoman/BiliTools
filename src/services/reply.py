"""
评论服务：获取视频评论、发表评论。
取代旧 `src/reply.py` 的 `BiliReply`，使用统一 BiliSession + 异常体系。
"""

import logging
from typing import Any, Optional

from src.api.session import BiliSession
from src.config.cookie import BiliCookies
from src.urls.comment_urls import CommentUrls
from src.util.bvid import bv2av

logger = logging.getLogger(__name__)


class ReplyService:
    """B 站视频评论服务。"""

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    @staticmethod
    def _normalize_sort(sort: str | int) -> int:
        """将评论排序方式转换为 B 站接口的 ``sort`` 参数。

        B 站评论列表接口使用 ``sort=0`` 表示按时间（最新），``sort=1``
        表示按点赞（最热）。同时接受常见的英文/中文别名，方便 CLI 和
        SDK 调用方使用，不把接口的数字约定泄漏到上层。
        """
        if isinstance(sort, bool):
            raise ValueError("sort 只能是 latest/newest 或 hot/popular（也可传 0/1）")
        if isinstance(sort, int):
            if sort in (0, 1):
                return sort
            raise ValueError("sort 只能是 0（最新）或 1（最热）")
        if not isinstance(sort, str):
            raise ValueError("sort 只能是字符串或整数")

        value = sort.strip().lower()
        if value in {"0", "latest", "new", "newest", "time", "按时间", "最新"}:
            return 0
        if value in {"1", "hot", "popular", "hottest", "like", "按热度", "最热"}:
            return 1
        raise ValueError("sort 只能是 latest/newest（最新）或 hot/popular（最热）")

    def get_comments(
        self,
        bvid: str = "",
        aid: int = 0,
        sort: str | int = "latest",
        max_count: int = -1,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        """获取视频评论。
        示例：comments = ReplyService().get_comments(bvid="BV1ov42117yC", sort="hot", max_count=10)

        :param bvid: 视频 BV 号（与 ``aid`` 二选一）
        :param aid: 视频 AV 号（与 ``bvid`` 二选一）
        :param sort: 排序方式。``latest``/``newest`` 或 0 为最新，
                     ``hot``/``popular`` 或 1 为最热
        :param max_count: 最多返回的评论数；默认 -1 表示获取全部评论。
                          传 0 时不请求接口并返回空列表。
        :param page_size: 每页请求数，接口允许的范围为 1~20；内部会按 20
                          分页，最后一页按 max_count 截断。
        :return: B 站接口 ``data.replies`` 中的评论字典列表。评论回复树的
                 ``replies`` 子列表会原样保留。
        :raises ValueError: 视频标识、排序方式或数量参数非法
        """
        if not bvid and not aid:
            raise ValueError("bvid 和 aid 不能同时为空")
        if max_count < -1:
            raise ValueError("max_count 只能为 -1 或非负整数")
        if page_size <= 0:
            raise ValueError("page_size 必须为正数")

        sort_value = self._normalize_sort(sort)
        if max_count == 0:
            return []

        oid = bv2av(bvid) if bvid else int(aid)
        # B 站该接口的 ps 上限是 20；即使调用方传入更大的 page_size，
        # 也不能依赖服务端接受它，否则会导致分页数量和 max_count 不稳定。
        request_size = min(page_size, 20)
        comments: list[dict[str, Any]] = []
        page = 1

        while True:
            data = self.session.get(
                CommentUrls.LIST,
                params={
                    "type": 1,  # 视频评论
                    "oid": oid,
                    "sort": sort_value,
                    "pn": page,
                    "ps": request_size,
                },
            )
            replies = data.get("replies") if isinstance(data, dict) else None
            if not isinstance(replies, list) or not replies:
                break

            comments.extend(replies)
            if max_count > 0 and len(comments) >= max_count:
                return comments[:max_count]

            # 少于请求页大小通常表示已经到达末页。若恰好整页返回，
            # 再请求一页确认接口确实没有更多内容。
            if len(replies) < request_size:
                break
            page += 1

        return comments if max_count == -1 else comments[:max_count]

    def get_replies(self, *args, **kwargs) -> list[dict[str, Any]]:
        """``get_comments`` 的兼容别名，沿用 B 站接口的 reply 命名。"""
        return self.get_comments(*args, **kwargs)

    def get_video_comments(self, *args, **kwargs) -> list[dict[str, Any]]:
        """``get_comments`` 的语义化别名。"""
        return self.get_comments(*args, **kwargs)

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
