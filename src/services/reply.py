"""
评论服务：获取/导出视频与动态评论、发表评论。
取代旧 `src/reply.py` 的 `BiliReply`，使用统一 BiliSession + 异常体系。
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from src.api.errors import BiliAPIError
from src.api.session import BiliSession
from src.config.cookie import BiliCookies
from src.config.path import COMMENT_OUTPUT_DIR
from src.models.comment_model import CommentExportResult
from src.urls.comment_urls import CommentUrls
from src.util.bvid import av2bv, bv2av

logger = logging.getLogger(__name__)

# 北京时间：导出时间与评论时间统一口径
_BEIJING = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(_BEIJING).isoformat(timespec="seconds")


def _format_ctime(value: Any) -> str:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return ""
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp, _BEIJING).strftime("%Y-%m-%d %H:%M")


def _sanitize_text(text: str) -> str:
    """孤立 UTF-16 代理字符替换为 U+FFFD，避免 UTF-8 写文件报错。"""
    if not any(0xD800 <= ord(char) <= 0xDFFF for char in text):
        return text

    chars: list[str] = []
    index = 0
    while index < len(text):
        code = ord(text[index])
        if 0xD800 <= code <= 0xDBFF:
            if index + 1 < len(text):
                low = ord(text[index + 1])
                if 0xDC00 <= low <= 0xDFFF:
                    chars.append(chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)))
                    index += 2
                    continue
            chars.append("\ufffd")
        elif 0xDC00 <= code <= 0xDFFF:
            chars.append("\ufffd")
        else:
            chars.append(text[index])
        index += 1
    return "".join(chars)


def _write_text_atomic(path: Path, text: str) -> None:
    """临时文件 + os.replace 原子写入；Windows 占用时短重试。"""
    text = _sanitize_text(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temp_path.write_text(text, encoding="utf-8", newline="\n")
    last_error: Optional[Exception] = None
    for attempt in range(5):
        try:
            os.replace(temp_path, path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05 * (attempt + 1))
    raise last_error  # type: ignore[misc]


_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>])")


def _md_inline(value: Any) -> str:
    text = str(value or "").replace("&", "&amp;")
    return _MD_SPECIAL.sub(r"\\\1", text)


def _comment_meta(comment: dict[str, Any]) -> list[str]:
    meta: list[str] = []
    ctime = _format_ctime(comment.get("ctime"))
    if ctime:
        meta.append(ctime)
    like = comment.get("like")
    if isinstance(like, int) and not isinstance(like, bool) and like > 0:
        meta.append(f"赞 {like}")
    return meta


def _comment_image_urls(content: dict[str, Any]) -> list[str]:
    pictures = content.get("pictures")
    if not isinstance(pictures, list):
        return []
    urls: list[str] = []
    for picture in pictures:
        if not isinstance(picture, dict):
            continue
        url = picture.get("img_src") or picture.get("url")
        if isinstance(url, str) and url:
            urls.append(url)
    return urls


def _append_quoted(lines: list[str], message: Any, indent: str = "") -> None:
    # 用引用块承载正文，避免评论里的 #/*/- 等被渲染成标题或列表；
    # 同时转义 HTML，防止评论内容在 Markdown 渲染器里注入标签。
    text = (
        str(message or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    for line in text.splitlines() or [""]:
        lines.append(f"{indent}> {line}")


def _render_reply(
    lines: list[str],
    reply: dict[str, Any],
    root_rpid: Any,
    names: dict[Any, str],
) -> None:
    member = reply.get("member") or {}
    content = reply.get("content") or {}
    uname = _md_inline(member.get("uname") or "未知用户")

    parent = reply.get("parent")
    parent_name = ""
    if parent and parent != root_rpid:
        parent_name = names.get(parent) or ""
        if parent_name:
            parent_name = _md_inline(parent_name)

    title = f"- **{uname}**"
    if parent_name:
        title += f"（回复 @{parent_name}）"
    meta = _comment_meta(reply)
    if meta:
        title += " · " + " · ".join(meta)
    lines.append(title)

    _append_quoted(lines, content.get("message"), indent="  ")
    for url in _comment_image_urls(content):
        lines.extend(["", f"  > ![评论图片]({url})"])
    lines.append("")


def _render_comment(lines: list[str], comment: dict[str, Any], index: int) -> None:
    member = comment.get("member") or {}
    content = comment.get("content") or {}
    uname = _md_inline(member.get("uname") or "未知用户")

    heading = f"## {index}. {uname}"
    if comment.get("is_pinned"):
        heading += "（置顶）"
    lines.extend([heading, ""])

    meta = _comment_meta(comment)
    if meta:
        lines.extend([" · ".join(meta), ""])

    _append_quoted(lines, content.get("message"))
    for url in _comment_image_urls(content):
        lines.extend(["", f"> ![评论图片]({url})"])
    lines.append("")

    replies = [
        reply for reply in (comment.get("replies") or []) if isinstance(reply, dict)
    ]
    if not replies:
        return

    names: dict[Any, str] = {
        comment.get("rpid"): member.get("uname") or "未知用户",
    }
    for reply in replies:
        reply_member = reply.get("member") or {}
        names[reply.get("rpid")] = reply_member.get("uname") or "未知用户"

    lines.extend([f"### 楼中楼（{len(replies)} 条）", ""])
    for reply in replies:
        _render_reply(lines, reply, comment.get("rpid"), names)


def _render_comments_markdown(
    bvid: str,
    aid: int,
    sort_name: str,
    comments: list[dict[str, Any]],
    fetched_at: str,
) -> str:
    sub_count = sum(
        len(comment.get("replies") or [])
        for comment in comments
        if isinstance(comment.get("replies"), list)
    )
    pinned_count = sum(1 for comment in comments if comment.get("is_pinned"))
    sort_label = "最热（hot）" if sort_name == "hot" else "最新（latest）"
    root_label = f"{len(comments)} 条"
    if pinned_count:
        root_label += f"（含置顶 {pinned_count} 条）"

    lines = [
        f"# {bvid} 评论存档",
        "",
        f"- 视频：[{bvid}](https://www.bilibili.com/video/{bvid})（aid: {aid}）",
        f"- 排序：{sort_label}",
        f"- 根评论：{root_label}",
        f"- 楼中楼：{sub_count} 条",
        f"- 导出时间：{fetched_at}",
        "",
        "---",
        "",
    ]
    for index, comment in enumerate(comments, 1):
        _render_comment(lines, comment, index)
    return "\n".join(lines).rstrip() + "\n"


class ReplyService:
    """B 站评论服务（获取、楼中楼、导出、发表）。"""

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

    @staticmethod
    def _as_reply_list(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _fetch_all_replies(
        self,
        url: str,
        params: dict[str, Any],
        max_count: int,
        page_size: int,
        include_pinned: bool = False,
        page_count_is_total: bool = False,
    ) -> list[dict[str, Any]]:
        """分页抓取 ``data.replies``，可选合并置顶评论并按 rpid 去重。

        置顶项会带 ``is_pinned: True``。``page_count_is_total`` 为 True 时
        用 ``data.page.count`` 作为总条数提前结束（楼中楼接口的 count 只统计
        该根评论）；根评论列表的 count 含楼中楼，不能用它判断是否还有下一页。
        """
        # B 站评论接口的 ps 上限是 20；即使调用方传入更大的 page_size，
        # 也不能依赖服务端接受它，否则会导致分页数量和 max_count 不稳定。
        request_size = min(page_size, 20)
        items: list[dict[str, Any]] = []
        seen: set[Any] = set()
        page = 1
        max_pages: Optional[int] = None

        while True:
            data = self.session.get(
                url, params={**params, "pn": page, "ps": request_size}
            )
            if not isinstance(data, dict):
                break

            total: Optional[int] = None
            page_info = data.get("page")
            count = page_info.get("count") if isinstance(page_info, dict) else None
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                if page_count_is_total:
                    total = count
                elif count > 0:
                    # 根评论的 count 含楼中楼，只能作为页数上界，防止接口
                    # 在越界页码上持续返回同一批数据导致死循环。
                    max_pages = (count + request_size - 1) // request_size

            if page == 1 and include_pinned:
                # 置顶评论不在 data.replies 里，需要单独合并；若同一 rpid
                # 也出现在普通列表里，以置顶位置为准并去重。
                for pinned in self._as_reply_list(data.get("top_replies")):
                    rpid = pinned.get("rpid")
                    if rpid is not None:
                        if rpid in seen:
                            continue
                        seen.add(rpid)
                    items.append({**pinned, "is_pinned": True})
                    if 0 < max_count <= len(items):
                        return items[:max_count]

            replies = self._as_reply_list(data.get("replies"))
            if not replies:
                break

            for reply in replies:
                rpid = reply.get("rpid")
                if rpid is not None:
                    if rpid in seen:
                        continue
                    seen.add(rpid)
                items.append(reply)
                if 0 < max_count <= len(items):
                    return items[:max_count]

            # 被删除/折叠的评论会让中间页不足 request_size，不能据此判定
            # 末页；持续翻页直到空页（有可靠 count 时提前结束）。
            if total is not None and len(items) >= total:
                break
            if max_pages is not None and page >= max_pages:
                break
            page += 1

        return items if max_count == -1 else items[:max_count]

    def _expand_sub_replies(
        self,
        oid: int,
        comment_type: int,
        comment: dict[str, Any],
        max_count: int,
        page_size: int,
    ) -> None:
        """把根评论的 ``replies`` 从接口内联的少量回复替换为楼中楼全量。"""
        if max_count == 0:
            comment["replies"] = []
            return

        inline = self._as_reply_list(comment.get("replies"))
        rcount = comment.get("rcount")
        if (
            isinstance(rcount, int)
            and not isinstance(rcount, bool)
            and len(inline) >= max(rcount, 0)
        ):
            comment["replies"] = inline
            return

        rpid = comment.get("rpid")
        if not isinstance(rpid, int) or isinstance(rpid, bool) or rpid <= 0:
            comment["replies"] = inline
            return

        try:
            replies = self.get_comment_replies(
                oid=oid,
                root=rpid,
                comment_type=comment_type,
                max_count=max_count,
                page_size=page_size,
            )
        except BiliAPIError as exc:
            # 单条楼中楼不可见/已删除时保留内联回复，不中断整批抓取。
            logger.warning("[ReplyService] 楼中楼获取失败，root=%s：%s", rpid, exc)
            replies = inline
        comment["replies"] = replies

    def get_comment_replies(
        self,
        oid: int,
        root: int,
        comment_type: int = 1,
        max_count: int = -1,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        """分页获取某条根评论下的全部楼中楼回复。

        B 站把根评论下的所有回复（包括回复楼中楼的回复）放在同一层返回，
        因此按 ``pn`` 翻页即可覆盖整棵回复树；接口的 ``page.count`` 可用来
        提前判断是否抓完。

        :param oid: 评论区 oid（视频为 aid）
        :param root: 根评论 rpid
        :param comment_type: 评论区类型，视频为 1，动态为 11/17
        :param max_count: 最多返回条数，默认 -1 表示不限制
        :param page_size: 每页请求数，接口最大为 20
        """
        self._validate_comment_options(max_count, page_size)
        if max_count == 0:
            return []
        return self._fetch_all_replies(
            CommentUrls.SUB_REPLY,
            {"type": comment_type, "oid": oid, "root": root},
            max_count=max_count,
            page_size=page_size,
            page_count_is_total=True,
        )

    def get_comments_by_oid(
        self,
        oid: int,
        comment_type: int,
        sort: str | int = "latest",
        max_count: int = -1,
        page_size: int = 20,
        with_sub_replies: bool = False,
        sub_max_count: int = -1,
        sub_page_size: int = 20,
    ) -> list[dict[str, Any]]:
        """按评论区类型和 oid 分页获取一级评论（公共入口）。

        视频评论（type=1）与动态评论（type=11/17）共用此实现；
        动态下载等已知 ``comment_id_str/comment_type`` 的调用方直接使用
        本方法，避免再次请求动态详情接口。

        :param with_sub_replies: 为 True 时逐条抓取楼中楼并写入根评论的
                                 ``replies`` 字段（替换接口内联的少量回复）
        :param sub_max_count: 每条根评论下最多获取的楼中楼条数，-1 为不限制
        :param sub_page_size: 楼中楼每页请求数，接口最大为 20
        """
        self._validate_comment_options(max_count, page_size)
        if with_sub_replies:
            self._validate_comment_options(sub_max_count, sub_page_size)
        sort_value = self._normalize_sort(sort)
        if max_count == 0:
            return []

        comments = self._fetch_all_replies(
            CommentUrls.LIST,
            {"type": comment_type, "oid": oid, "sort": sort_value},
            max_count=max_count,
            page_size=page_size,
            include_pinned=True,
        )
        if with_sub_replies:
            for comment in comments:
                self._expand_sub_replies(
                    oid=oid,
                    comment_type=comment_type,
                    comment=comment,
                    max_count=sub_max_count,
                    page_size=sub_page_size,
                )
        return comments

    def get_video_comments(
        self,
        bvid: str = "",
        aid: int = 0,
        sort: str | int = "latest",
        max_count: int = -1,
        page_size: int = 20,
        with_sub_replies: bool = False,
        sub_max_count: int = -1,
        sub_page_size: int = 20,
    ) -> list[dict[str, Any]]:
        """获取视频评论。

        :param bvid: 视频 BV 号（与 ``aid`` 二选一）
        :param aid: 视频 AV 号（与 ``bvid`` 二选一）
        :param sort: 排序方式。``latest``/``newest`` 或 0 为最新，
                     ``hot``/``popular`` 或 1 为最热
        :param max_count: 最多返回的根评论数（置顶评论计入）；默认 -1 表示
                          获取全部可见评论。传 0 时不请求接口并返回空列表。
        :param page_size: 每页请求数，接口允许的范围为 1~20；内部会按 20
                          分页，最后一页按 max_count 截断。
        :param with_sub_replies: 为 True 时抓取每条根评论下的全部楼中楼，
                                 写入其 ``replies`` 字段
        :param sub_max_count: 每条根评论下最多获取的楼中楼条数，-1 为不限制
        :param sub_page_size: 楼中楼每页请求数，接口最大为 20
        :return: 根评论字典列表（含置顶评论），``replies`` 默认为接口内联
                 回复；开启 ``with_sub_replies`` 后为楼中楼全量。
        """
        if not bvid and not aid:
            raise ValueError("bvid 和 aid 不能同时为空")
        oid = bv2av(bvid) if bvid else int(aid)
        return self.get_comments_by_oid(
            oid=oid,
            comment_type=1,
            sort=sort,
            max_count=max_count,
            page_size=page_size,
            with_sub_replies=with_sub_replies,
            sub_max_count=sub_max_count,
            sub_page_size=sub_page_size,
        )

    def get_comments(self, *args, **kwargs) -> list[dict[str, Any]]:
        """获取视频评论的兼容入口。

        保留原有 ``get_comments`` API；新代码也可以使用语义更明确的
        ``get_video_comments``。
        """
        return self.get_video_comments(*args, **kwargs)

    def export_video_comments(
        self,
        bvid: str = "",
        aid: int = 0,
        sort: str | int = "latest",
        max_count: int = -1,
        with_sub_replies: bool = True,
        sub_max_count: int = -1,
        save_dir: str | Path | None = None,
    ) -> CommentExportResult:
        """抓取视频评论并导出为 JSON + Markdown。

        默认抓取全部可见根评论（含置顶）以及每条根评论下的全部楼中楼。
        文件落在 ``save_dir/{bvid}/``（默认 ``output/comments/{bvid}/``）：
        ``comments.json`` 保留接口原始嵌套结构，``comments.md`` 便于阅读。
        同一视频重复导出会覆盖这两个文件。

        :param bvid: 视频 BV 号（与 ``aid`` 二选一）
        :param aid: 视频 AV 号（与 ``bvid`` 二选一）
        :param sort: ``latest``/``0`` 最新，``hot``/``1`` 最热
        :param max_count: 根评论上限（置顶计入），-1 表示全部
        :param with_sub_replies: 是否抓取楼中楼，默认 True
        :param sub_max_count: 每条根评论下的楼中楼上限，-1 表示全部
        :param save_dir: 输出根目录，默认 ``output/comments``
        """
        if not bvid and not aid:
            raise ValueError("bvid 和 aid 不能同时为空")

        if bvid:
            bvid = bvid.strip()
            if not bvid:
                raise ValueError("bvid 不能为空")
            try:
                oid = bv2av(bvid)
            except (AssertionError, IndexError, ValueError) as exc:
                raise ValueError(f"非法的 BV 号：{bvid}") from exc
        else:
            try:
                oid = int(aid)
            except (TypeError, ValueError) as exc:
                raise ValueError("aid 必须是整数") from exc
        if oid <= 0:
            raise ValueError("视频 ID 必须为正整数")
        bvid = av2bv(oid)

        sort_value = self._normalize_sort(sort)
        sort_name = "hot" if sort_value == 1 else "latest"

        comments = self.get_comments_by_oid(
            oid=oid,
            comment_type=1,
            sort=sort_value,
            max_count=max_count,
            with_sub_replies=with_sub_replies,
            sub_max_count=sub_max_count,
        )
        root_count = len(comments)
        sub_count = sum(
            len(self._as_reply_list(comment.get("replies"))) for comment in comments
        )
        pinned_count = sum(1 for comment in comments if comment.get("is_pinned"))
        fetched_at = _now_iso()

        base_dir = Path(save_dir) if save_dir is not None else Path(COMMENT_OUTPUT_DIR)
        export_dir = base_dir / bvid
        json_path = export_dir / "comments.json"
        markdown_path = export_dir / "comments.md"

        payload = {
            "version": 1,
            "platform": "bilibili",
            "bvid": bvid,
            "aid": oid,
            "oid": oid,
            "comment_type": 1,
            "sort": sort_name,
            "with_sub_replies": bool(with_sub_replies),
            "root_count": root_count,
            "sub_count": sub_count,
            "pinned_count": pinned_count,
            "fetched_at": fetched_at,
            "items": comments,
        }
        _write_text_atomic(
            json_path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )
        _write_text_atomic(
            markdown_path,
            _render_comments_markdown(
                bvid=bvid,
                aid=oid,
                sort_name=sort_name,
                comments=comments,
                fetched_at=fetched_at,
            ),
        )

        return CommentExportResult(
            export_dir=export_dir,
            json_path=json_path,
            markdown_path=markdown_path,
            bvid=bvid,
            aid=oid,
            sort=sort_name,
            root_count=root_count,
            sub_count=sub_count,
            pinned_count=pinned_count,
            fetched_at=fetched_at,
        )

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
        with_sub_replies: bool = False,
        sub_max_count: int = -1,
        sub_page_size: int = 20,
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
        :param max_count: 最大返回的根评论数（置顶评论计入），默认 -1 表示不限制
        :param page_size: 每页请求数，接口最大为 20
        :param with_sub_replies: 为 True 时抓取每条根评论下的全部楼中楼
        :param sub_max_count: 每条根评论下最多获取的楼中楼条数，-1 为不限制
        :param sub_page_size: 楼中楼每页请求数，接口最大为 20
        :return: 根评论字典列表（含置顶评论），``replies`` 为内联或全量楼中楼
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

        return self.get_comments_by_oid(
            oid=comment_oid,
            comment_type=comment_type,
            sort=sort,
            max_count=max_count,
            page_size=page_size,
            with_sub_replies=with_sub_replies,
            sub_max_count=sub_max_count,
            sub_page_size=sub_page_size,
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
