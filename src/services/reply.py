"""
评论服务：获取视频/动态评论、发表评论。
取代旧 `src/reply.py` 的 `BiliReply`，使用统一 BiliSession + 异常体系。
"""

import logging
import re
from typing import Any, Optional
from urllib.parse import urlparse

from src.api.session import BiliSession
from src.config.cookie import BiliCookies
from src.urls.comment_urls import CommentUrls
from src.util.bvid import bv2av

logger = logging.getLogger(__name__)


class ReplyService:
    """B 站评论服务。"""

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

    @staticmethod
    def _validate_comment_options(max_count: int, page_size: int) -> None:
        if max_count < -1:
            raise ValueError("max_count 只能为 -1 或非负整数")
        if page_size <= 0:
            raise ValueError("page_size 必须为正数")

    def _get_comments_by_oid(
        self,
        oid: int,
        comment_type: int,
        sort: str | int = "latest",
        max_count: int = -1,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        """按评论区类型和 oid 分页获取一级评论。"""
        self._validate_comment_options(max_count, page_size)
        sort_value = self._normalize_sort(sort)
        if max_count == 0:
            return []

        # B 站该接口的 ps 上限是 20；即使调用方传入更大的 page_size，
        # 也不能依赖服务端接受它，否则会导致分页数量和 max_count 不稳定。
        request_size = min(page_size, 20)
        comments: list[dict[str, Any]] = []
        page = 1

        while True:
            data = self.session.get(
                CommentUrls.LIST,
                params={
                    "type": comment_type,
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
            if 0 < max_count <= len(comments):
                return comments[:max_count]

            # 少于请求页大小通常表示已经到达末页。若恰好整页返回，
            # 再请求一页确认接口确实没有更多内容。
            if len(replies) < request_size:
                break
            page += 1

        return comments if max_count == -1 else comments[:max_count]

    def get_video_comments(
        self,
        bvid: str = "",
        aid: int = 0,
        sort: str | int = "latest",
        max_count: int = -1,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        """获取视频评论。

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
        """
        if not bvid and not aid:
            raise ValueError("bvid 和 aid 不能同时为空")
        oid = bv2av(bvid) if bvid else int(aid)
        return self._get_comments_by_oid(
            oid=oid,
            comment_type=1,
            sort=sort,
            max_count=max_count,
            page_size=page_size,
        )

    def get_comments(self, *args, **kwargs) -> list[dict[str, Any]]:
        """获取视频评论的兼容入口。

        保留原有 ``get_comments`` API；新代码也可以使用语义更明确的
        ``get_video_comments``。
        """
        return self.get_video_comments(*args, **kwargs)

    @staticmethod
    def _resolve_dynamic_id(dynamic_id: int | str) -> int:
        """从动态 ID 或 ``/opus/<id>`` 链接中提取动态 ID。"""
        if isinstance(dynamic_id, bool):
            raise ValueError("dynamic_id 必须是动态 ID 或 opus 链接")
        if isinstance(dynamic_id, int):
            value = dynamic_id
        elif isinstance(dynamic_id, str):
            value = dynamic_id.strip()
            if not value:
                raise ValueError("dynamic_id 不能为空")
            if "://" in value:
                parsed = urlparse(value)
                match = re.fullmatch(r"/opus/(\d+)/?", parsed.path)
                if not match:
                    raise ValueError("动态链接必须是 https://www.bilibili.com/opus/<id>")
                value = match.group(1)
            if not value.isdigit():
                raise ValueError("dynamic_id 必须是正整数或 opus 链接")
            value = int(value)
        else:
            raise ValueError("dynamic_id 必须是动态 ID 或 opus 链接")

        if value <= 0:
            raise ValueError("dynamic_id 必须是正整数")
        return value

    def get_dynamic_comments(
        self,
        dynamic_id: int | str,
        sort: str | int = "latest",
        max_count: int = -1,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        """获取动态（包括 ``bilibili.com/opus/<id>``）的评论。

        新版 opus 链接的 URL ID 不一定就是评论接口的 ``oid``。方法会先
        调用动态详情接口，读取 ``item.basic.comment_id_str`` 和
        ``item.basic.comment_type``，再分页请求评论列表。因此既支持
        图文动态（通常 type=11），也兼容纯文字/分享动态（通常 type=17）。

        :param dynamic_id: 动态 ID，或形如 ``https://www.bilibili.com/opus/<id>``
                            的动态链接
        :param sort: ``latest``/``newest`` 或 0 为最新，``hot``/``popular``
                     或 1 为最热
        :param max_count: 最大返回条数，默认 -1 表示不限制
        :param page_size: 每页请求数，接口最大为 20
        :return: B 站接口 ``data.replies`` 中的评论字典列表
        """
        opus_id = self._resolve_dynamic_id(dynamic_id)
        # 不同于视频，opus URL ID 可能是动态本体 ID，不能直接作为评论 oid。
        detail = self.session.get(CommentUrls.DYNAMIC_DETAIL, params={"id": opus_id})
        item = detail.get("item") if isinstance(detail, dict) else None
        basic = item.get("basic") if isinstance(item, dict) else None
        if not isinstance(basic, dict):
            raise ValueError("动态详情中缺少评论区信息")

        comment_oid = basic.get("comment_id_str") or basic.get("comment_id")
        comment_type = basic.get("comment_type")
        try:
            comment_oid = int(comment_oid)
            comment_type = int(comment_type)
        except (TypeError, ValueError) as exc:
            raise ValueError("动态详情中的评论区信息无效") from exc
        if comment_oid <= 0 or comment_type <= 0:
            raise ValueError("动态详情中的评论区信息无效")

        return self._get_comments_by_oid(
            oid=comment_oid,
            comment_type=comment_type,
            sort=sort,
            max_count=max_count,
            page_size=page_size,
        )

    def get_opus_comments(self, *args, **kwargs) -> list[dict[str, Any]]:
        """``get_dynamic_comments`` 的语义化别名。"""
        return self.get_dynamic_comments(*args, **kwargs)

    def get_dynamic_replies(self, *args, **kwargs) -> list[dict[str, Any]]:
        """``get_dynamic_comments`` 的兼容别名。"""
        return self.get_dynamic_comments(*args, **kwargs)

    def get_replies(self, *args, **kwargs) -> list[dict[str, Any]]:
        """``get_comments`` 的兼容别名，沿用 B 站接口的 reply 命名。"""
        return self.get_video_comments(*args, **kwargs)

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
