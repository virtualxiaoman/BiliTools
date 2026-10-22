"""
私信服务：发送私信、读取历史私信、导出私信记录。
取代旧 `src/message.py` 的 `BiliMessage`，使用统一 BiliSession + 异常体系。

[导出结构]
    output/message/{我的mid}/{好友mid}/
        messages.json   完整结构化数据（同时作为增量同步缓存）
        messages.md     可读聊天记录
        assets/         聊天中的图片等资源

- 默认增量同步：读取已有 messages.json，只向接口拉取新增消息，合并后同时重写 JSON 和 Markdown；
- force=True 时不使用缓存，重新拉取全部消息并重新下载资源；
- JSON 保留接口原始字段（msg_type / content / msg_status 等），Markdown 便于直接浏览。
"""

import hashlib
import html
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from src.api.auth import get_dev_id, get_timestamp
from src.api.errors import BiliAPIError
from src.api.session import BiliSession
from src.config.cookie import BiliCookies
from src.config.path import MESSAGE_OUTPUT_DIR
from src.models.message_model import MessageExportResult
from src.services.login import LoginService
from src.urls.message_urls import MessageUrls
from src.urls.user_urls import UserUrls
from src.util.downloader import download_stream
from src.util.progress import MessageExportProgress

logger = logging.getLogger(__name__)

_BEIJING = timezone(timedelta(hours=8))

# get_sessions 的会话类型（BAC 文档）：4=所有、7=所有系统消息。
# 4 不支持时间游标翻页，因此“全部”通过其余分类分别翻页后合并去重实现。
MESSAGE_GROUP_NAMES = {
    1: "用户与系统",
    2: "未关注人",
    3: "粉丝团",
    5: "被拦截",
    6: "花火商单",
    7: "系统消息",
    8: "陌生人",
    9: "关注的人与系统",
}
ALL_MESSAGE_GROUPS = tuple(MESSAGE_GROUP_NAMES)
# 默认导出除“所有系统消息”外的全部分组；分组 1/9 中的纯系统会话仍会按
# system_msg_type 过滤掉，除非调用方显式传入 7。
DEFAULT_MESSAGE_GROUPS = tuple(group for group in ALL_MESSAGE_GROUPS if group != 7)

_GROUP_ALIASES = {
    "user": 1, "用户": 1, "用户与系统": 1,
    "unfollowed": 2, "未关注人": 2,
    "fan_group": 3, "fans": 3, "粉丝团": 3,
    "intercepted": 5, "blocked": 5, "被拦截": 5,
    "business": 6, "花火": 6, "花火商单": 6,
    "system": 7, "系统": 7, "系统消息": 7,
    "stranger": 8, "陌生人": 8,
    "followed": 9, "关注": 9, "关注的人与系统": 9,
}

_SESSION_PAGE_SIZE = 100  # get_sessions 单页上限
_MAX_MESSAGE_PAGE_SIZE = 2000  # fetch_session_msgs 单页上限
_DEFAULT_MESSAGE_PAGE_SIZE = 200
_DEFAULT_REQUEST_INTERVAL = 0.2  # 翻页间隔，降低连续请求触发风控的概率

_IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "avif"}
_IMAGE_FIELDS = (
    ("thumb", "封面"),
    ("cover", "封面"),
    ("image_url", "图片"),
    ("poster", "封面"),
    ("face", "头像"),
    ("avatar", "头像"),
)


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _beijing_datetime(ts) -> Optional[datetime]:
    value = _to_int(ts)
    if value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value, _BEIJING)
    except (OSError, OverflowError, ValueError):
        return None


def _now_text() -> str:
    return datetime.now(_BEIJING).strftime("%Y-%m-%d %H:%M:%S")


def _sanitize_text(text: str) -> str:
    """规范化 UTF-16 代理字符：合法代理对合并为 emoji，孤立代理替换为 U+FFFD。

    B 站部分私信 content 里可能出现只有高/低半边的代理字符（如 ``\\ud83d``），
    Python 解析后会得到孤立代理；直接以 UTF-8 写文件会抛
    ``UnicodeEncodeError: surrogates not allowed``。
    """
    if not isinstance(text, str):
        return text
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


def _sanitize_data(value):
    """递归清洗 JSON 数据中的孤立代理字符。"""
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, dict):
        return {
            _sanitize_text(key) if isinstance(key, str) else key: _sanitize_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_data(item) for item in value)
    return value


def _parse_content(raw) -> dict:
    """把消息的 content JSON 字符串解析为 dict；失败时按纯文本处理。"""
    if isinstance(raw, dict):
        return _sanitize_data(raw)
    if not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {"content": _sanitize_text(raw)}
    return _sanitize_data(parsed) if isinstance(parsed, dict) else {"content": _sanitize_text(raw)}


def _is_http_url(value) -> bool:
    return isinstance(value, str) and value.strip().startswith(("http://", "https://"))


def _html_multiline(text: str) -> str:
    """HTML 转义并把换行转成 <br>，避免 Markdown 把气泡内的空行截断。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return html.escape(normalized).replace("\n", "<br>")


def _message_images(message: dict) -> list[dict]:
    """提取消息中可本地化的图片资源：图片消息原图 + 卡片封面/头像。"""
    content = _parse_content(message.get("content"))
    msg_type = _to_int(message.get("msg_type"))
    images: list[dict] = []

    def add(url, alt: str) -> None:
        if not _is_http_url(url):
            return
        url = url.strip()
        if all(image["url"] != url for image in images):
            images.append({"url": url, "alt": alt})

    if msg_type == 2:
        add(content.get("url") or content.get("origin_url"), "图片")
        return images

    for field, alt in _IMAGE_FIELDS:
        value = content.get(field)
        if isinstance(value, list):
            for item in value:
                add(item, alt)
        else:
            add(value, alt)
    for field in ("image_urls", "images"):
        value = content.get(field)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    add(item.get("url") or item.get("image_url"), "图片")
                else:
                    add(item, "图片")
    return images


def _message_text(message: dict) -> str:
    """提取消息正文（不含图片和跳转链接）。"""
    content = _parse_content(message.get("content"))
    msg_type = _to_int(message.get("msg_type"))
    if msg_type == 2:
        return ""
    parts: list[str] = []
    for key in ("title", "text", "desc", "summary", "content", "message"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            value = value.strip()
            if value not in parts:
                parts.append(value)
    text = "\n\n".join(parts)
    # 类型 5 的 content 常常只是占位数字，不是可读正文。
    if msg_type == 5 and text.isdigit():
        return ""
    return text


def _message_link(message: dict, images: Optional[list[dict]] = None) -> str:
    """消息中的跳转链接（视频/专栏/活动卡片等）。"""
    content = _parse_content(message.get("content"))
    for key in ("jump_url", "jump_uri"):
        value = content.get(key)
        if _is_http_url(value):
            return value.strip()
    url = content.get("url")
    if images is None:
        images = _message_images(message)
    if _is_http_url(url) and all(image["url"] != url.strip() for image in images):
        return url.strip()
    return ""


def _message_key(message: dict):
    seqno = _to_int(message.get("msg_seqno"))
    if seqno:
        return ("seqno", seqno)
    msg_key = message.get("msg_key")
    if msg_key:
        return ("key", msg_key)
    return (
        "raw",
        _to_int(message.get("timestamp")),
        _to_int(message.get("sender_uid")),
        _to_int(message.get("msg_type")),
        str(message.get("content", "")),
    )


def _message_key_str(message: dict) -> str:
    return "|".join(str(part) for part in _message_key(message))


def _sort_messages(messages: list[dict]) -> list[dict]:
    """按时间正序去重；msg_seqno 是服务端的全局递增序号。"""
    unique: dict = {}
    for message in messages:
        if not isinstance(message, dict):
            continue
        unique.setdefault(_message_key(message), message)

    def sort_key(message: dict):
        return (
            _to_int(message.get("timestamp")),
            _to_int(message.get("msg_seqno")),
        )

    return sorted(unique.values(), key=sort_key)


def _image_extension(url: str, content: dict) -> str:
    suffix = Path(urlparse(url).path).suffix.lower().lstrip(".")
    if suffix in _IMAGE_EXTS:
        return "jpg" if suffix == "jpeg" else suffix
    hint = str(content.get("imageType") or content.get("image_type") or "").lower().lstrip(".")
    if hint in _IMAGE_EXTS:
        return "jpg" if hint == "jpeg" else hint
    return "jpg"


def _asset_relative_path(message: dict, index: int, ext: str) -> str:
    """资源文件名：优先用消息序号；无序号时用时间戳 + 消息键哈希。"""
    seqno = _to_int(message.get("msg_seqno"))
    if seqno:
        stem = str(seqno)
    else:
        digest = hashlib.sha1(_message_key_str(message).encode("utf-8")).hexdigest()[:12]
        stem = f"{_to_int(message.get('timestamp'))}_{digest}"
    return f"assets/{stem}_{index}.{ext}"


def _write_text_atomic(path: Path, text: str) -> None:
    """临时文件 + os.replace 原子写入；Windows 占用时短重试。"""
    sanitized = _sanitize_text(text)
    if sanitized != text:
        logger.warning(
            "[MessageService] %s 含非法 Unicode 代理字符，已替换为 U+FFFD", path.name
        )
    text = sanitized
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


def _sender_label(message: dict, account_mid: int, account_name: str,
                  session_type: int, system_session: bool,
                  names: dict[int, str]) -> str:
    sender_uid = _to_int(message.get("sender_uid"))
    if sender_uid == account_mid:
        return account_name or "我"
    if system_session:
        return "系统消息"
    name = names.get(sender_uid)
    if name:
        return name
    if session_type == 2:
        return f"uid:{sender_uid}"
    return f"用户{sender_uid}"


def _message_video_card(message: dict) -> Optional[dict]:
    """解析 msg_type=11（视频消息）的 content；非视频返回 None。"""
    if _to_int(message.get("msg_type")) != 11:
        return None
    content = _parse_content(message.get("content"))

    bvid = content.get("bvid")
    bvid = bvid.strip() if isinstance(bvid, str) else ""
    rid = _to_int(content.get("rid"))
    if bvid:
        video_url = f"https://www.bilibili.com/video/{bvid}"
    elif rid > 0:
        video_url = f"https://www.bilibili.com/video/av{rid}"
    else:
        video_url = ""

    title = content.get("title")
    title = title.strip() if isinstance(title, str) else ""
    if not title:
        title = f"视频 {bvid}" if bvid else (f"视频 av{rid}" if rid > 0 else "视频")
    desc = content.get("desc")
    desc = desc.strip() if isinstance(desc, str) else ""
    cover = content.get("cover")
    cover = cover.strip() if _is_http_url(cover) else ""

    attach_text = ""
    attach = content.get("attach_msg")
    if isinstance(attach, dict):
        value = attach.get("content")
        attach_text = value.strip() if isinstance(value, str) else ""
    elif isinstance(attach, str):
        attach_text = attach.strip()

    return {
        "title": title,
        "desc": desc,
        "cover": cover,
        "bvid": bvid,
        "rid": rid,
        "url": video_url,
        "view": _to_int(content.get("view")),
        "danmaku": _to_int(content.get("danmaku")),
        "duration": _to_int(content.get("times")),
        "pub_date": _to_int(content.get("pub_date")),
        "attach_text": attach_text,
    }


def _format_count(value) -> str:
    value = _to_int(value)
    if value >= 100_000_000:
        return f"{value / 100_000_000:.1f}亿"
    if value >= 10_000:
        return f"{value / 10_000:.1f}万"
    return str(value)


def _format_duration(seconds) -> str:
    total = max(0, _to_int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _video_card_html(video: dict, assets: dict, key: str,
                     images: list[dict]) -> str:
    url = video["url"]
    title_html = _html_multiline(video["title"])
    if url:
        href = html.escape(url, quote=True)
        title_html = (
            f'<a href="{href}" target="_blank" rel="noreferrer" '
            f'style="color:#1f2329; text-decoration:none; font-weight:600;">'
            f'{title_html}</a>'
        )
    else:
        title_html = f'<span style="font-weight:600;">{title_html}</span>'

    parts: list[str] = []
    if images:
        cover_index = next(
            (index for index, image in enumerate(images)
             if video["cover"] and image["url"] == video["cover"]),
            0,
        )
        asset = assets.get(f"{key}:{cover_index}") or {}
        src = asset.get("file") or images[cover_index]["url"]
        img_html = (
            f'<img src="{html.escape(src, quote=True)}" alt="视频封面" '
            f'style="width:100%; max-height:180px; object-fit:cover; '
            f'border-radius:8px; display:block; margin-bottom:8px;">'
        )
        if url:
            img_html = (
                f'<a href="{html.escape(url, quote=True)}" target="_blank" '
                f'rel="noreferrer">{img_html}</a>'
            )
        parts.append(img_html)

    parts.append(f'<div style="line-height:1.4;">{title_html}</div>')

    stats: list[str] = []
    if video["view"]:
        stats.append(f'播放 {_format_count(video["view"])}')
    if video["danmaku"]:
        stats.append(f'弹幕 {_format_count(video["danmaku"])}')
    if video["duration"]:
        stats.append(f'时长 {_format_duration(video["duration"])}')
    published = _beijing_datetime(video["pub_date"])
    if published:
        stats.append(published.strftime("%Y-%m-%d"))
    if stats:
        parts.append(
            '<div style="font-size:12px; color:#7a828e; margin-top:5px;">'
            + " · ".join(stats)
            + "</div>"
        )
    if video["bvid"]:
        parts.append(
            '<div style="font-size:12px; color:#8a919f; margin-top:3px;">'
            f'BV号：{html.escape(video["bvid"])}</div>'
        )

    if video["desc"]:
        parts.append(
            '<div style="font-size:13px; color:#4e5969; margin-top:6px; '
            f'white-space:pre-wrap;">{_html_multiline(video["desc"])}</div>'
        )
    if video["attach_text"]:
        parts.append(
            '<div style="font-size:12px; color:#7a828e; margin-top:6px; '
            'border-top:1px solid rgba(0,0,0,0.06); padding-top:6px; '
            f'white-space:pre-wrap;">附言：{_html_multiline(video["attach_text"])}</div>'
        )
    return '<div style="min-width:200px;">' + "".join(parts) + "</div>"


def _message_html_body(message: dict, assets: dict) -> str:
    key = _message_key_str(message)
    video = _message_video_card(message)
    if video is not None:
        return _video_card_html(video, assets, key, _message_images(message))

    blocks: list[str] = []
    images = _message_images(message)
    text = _message_text(message)
    if text:
        blocks.append(
            '<div style="white-space:pre-wrap; line-height:1.6;">'
            f"{_html_multiline(text)}</div>"
        )

    link = _message_link(message, images)
    if link and link not in text:
        blocks.append(
            f'<div><a href="{html.escape(link, quote=True)}" target="_blank" '
            'rel="noreferrer" style="color:#1677ff; text-decoration:none;">'
            "查看链接</a></div>"
        )

    for index, image in enumerate(images):
        asset = assets.get(f"{key}:{index}") or {}
        src = asset.get("file") or image["url"]
        blocks.append(
            f'<img src="{html.escape(src, quote=True)}" '
            f'alt="{html.escape(image["alt"], quote=True)}" '
            'style="max-width:100%; border-radius:8px; display:block; margin-top:6px;">'
        )

    if not blocks:
        msg_type = _to_int(message.get("msg_type"))
        label = "撤回/系统提示" if msg_type == 5 else f"msg_type={msg_type}"
        blocks.append(f'<span style="color:#8a919f;">[{label}]</span>')
    return "".join(blocks)


def _bubble_html(message: dict, account_mid: int, account_name: str,
                 session_type: int, system_session: bool, assets: dict,
                 names: dict[int, str]) -> str:
    moment = _beijing_datetime(message.get("timestamp"))
    time_label = moment.strftime("%H:%M:%S") if moment else "未知时间"
    sender = _sender_label(
        message, account_mid, account_name, session_type, system_session, names
    )
    status = " · 已撤回" if _to_int(message.get("msg_status")) == 1 else ""
    header = html.escape(f"{sender} · {time_label}{status}")
    is_me = _to_int(message.get("sender_uid")) == account_mid

    if system_session:
        row_style = "display:flex; justify-content:center; margin:10px 0;"
        bubble_style = (
            "max-width:76%; background:#f2f3f5; color:#1f2329; "
            "border-radius:12px; padding:9px 13px; font-size:14px; line-height:1.6; "
            "box-shadow:0 1px 2px rgba(0,0,0,0.05); word-break:break-word;"
        )
        header_align = "center"
    elif is_me:
        row_style = "display:flex; justify-content:flex-end; margin:10px 0;"
        bubble_style = (
            "max-width:72%; background:#d6eaff; color:#1f2329; "
            "border-radius:14px 14px 2px 14px; padding:9px 13px; font-size:14px; "
            "line-height:1.6; box-shadow:0 1px 2px rgba(0,0,0,0.06); "
            "word-break:break-word;"
        )
        header_align = "right"
    else:
        row_style = "display:flex; justify-content:flex-start; margin:10px 0;"
        bubble_style = (
            "max-width:72%; background:#d9f7be; color:#1f2329; "
            "border-radius:14px 14px 14px 2px; padding:9px 13px; font-size:14px; "
            "line-height:1.6; box-shadow:0 1px 2px rgba(0,0,0,0.06); "
            "word-break:break-word;"
        )
        header_align = "left"

    body = _message_html_body(message, assets)
    return (
        f'<div style="{row_style}">'
        f'<div style="{bubble_style}">'
        f'<div style="font-size:12px; color:#7a828e; margin-bottom:5px; '
        f'text-align:{header_align};">{header}</div>'
        f"{body}</div></div>"
    )


def _render_markdown(account_mid: int, account_name: str, talker_id: int,
                     session_type: int, session: Optional[dict],
                     messages: list[dict], assets: dict,
                     names: dict[int, str], exported_at: str) -> str:
    session = session or {}
    system_session = bool(_to_int(session.get("system_msg_type")))
    group_name = session.get("group_name") or ""
    if system_session:
        display = "系统消息"
        title = "# 系统消息记录"
        session_label = "系统消息"
    else:
        if session_type == 2:
            display = f"粉丝团 {group_name}" if group_name else f"粉丝团 {talker_id}"
            title = f"# 与 {display} 的私信记录"
            session_label = "粉丝团"
        else:
            display = f"用户 {talker_id}"
            title = f"# 与 {display} 的私信记录"
            session_label = "用户"

    peer_name = names.get(talker_id, "")
    peer_line = f"- 对方 mid：{talker_id}"
    if peer_name:
        peer_line += f"（{peer_name}）"
    lines = [
        title,
        "",
        f"- 我的 mid：{account_mid}（{account_name}）",
        peer_line,
        f"- 会话类型：{session_label}",
        f"- 消息数：{len(messages)}",
        f"- 最近同步：{exported_at}",
        "",
        "---",
        "",
    ]
    if not messages:
        lines.append("_暂无消息_")
        return "\n".join(lines) + "\n"

    current_date = ""
    for message in messages:
        moment = _beijing_datetime(message.get("timestamp"))
        date_label = moment.strftime("%Y-%m-%d") if moment else "未知日期"
        if date_label != current_date:
            if current_date:
                lines.append("")
            lines.extend([
                f'<div style="text-align:center; margin:18px 0 10px; '
                f'color:#8a919f; font-size:12px;">{date_label}</div>',
                "",
            ])
            current_date = date_label

        lines.extend([
            _bubble_html(
                message,
                account_mid=account_mid,
                account_name=account_name,
                session_type=session_type,
                system_session=system_session,
                assets=assets,
                names=names,
            ),
            "",
        ])

    return "\n".join(lines).rstrip() + "\n"


def _load_conversation_cache(friend_dir: Path, account_mid: int,
                             talker_id: int, session_type: int
                             ) -> tuple[list[dict], dict, Optional[dict], dict[int, str]]:
    """读取 messages.json 缓存；损坏或身份不匹配时按无缓存处理。"""
    json_path = friend_dir / "messages.json"
    if not json_path.exists():
        return [], {}, None, {}
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        logger.warning("[MessageService] 读取缓存失败，将全量拉取：%s（%s）", json_path, exc)
        return [], {}, None, {}
    if not isinstance(payload, dict):
        logger.warning("[MessageService] 缓存格式异常，将全量拉取：%s", json_path)
        return [], {}, None, {}

    cached_account = _to_int(payload.get("account_mid"))
    cached_talker = _to_int(payload.get("talker_id"))
    cached_session_type = _to_int(payload.get("session_type"))
    if cached_account and cached_account != account_mid:
        logger.warning("[MessageService] 缓存账号不匹配，将全量拉取：%s", json_path)
        return [], {}, None, {}
    if cached_talker and cached_talker != talker_id:
        logger.warning("[MessageService] 缓存对象不匹配，将全量拉取：%s", json_path)
        return [], {}, None, {}
    if cached_session_type and cached_session_type != session_type:
        logger.warning("[MessageService] 缓存会话类型不匹配，将全量拉取：%s", json_path)
        return [], {}, None, {}

    messages = [item for item in (payload.get("messages") or []) if isinstance(item, dict)]
    assets = payload.get("assets") if isinstance(payload.get("assets"), dict) else {}
    session = payload.get("session") if isinstance(payload.get("session"), dict) else None
    if session is not None:
        session = _sanitize_data(session)
    names: dict[int, str] = {}
    raw_names = payload.get("names")
    if isinstance(raw_names, dict):
        for key, value in raw_names.items():
            uid = _to_int(key)
            name = value.strip() if isinstance(value, str) else ""
            if uid > 0 and name:
                names[uid] = _sanitize_text(name)
    return messages, assets, session, names


class MessageService:
    """B 站私信服务。"""

    def __init__(self, session: Optional[BiliSession] = None, default_dir=None):
        self.session = session if session is not None else BiliSession()
        self.default_dir = Path(default_dir) if default_dir is not None else MESSAGE_OUTPUT_DIR

    # ---- 发送私信 ----

    def send_msg(self, receiver_uid: int, content: str,
                 sender_uid: Optional[int] = None, msg_type: int = 1) -> dict:
        """发送私信。

        :param receiver_uid: 接收者mid
        :param content: 内容
        :param sender_uid: 发送者mid，为空时自动使用本地默认登录账号的mid
        :param msg_type: 消息类型。1:发送文字 2:发送图片 5:撤回消息
        :return: 接口返回的 data 字典
        """
        if sender_uid is None:
            sender_uid = LoginService(self.session).get_mid()
            if sender_uid is None:
                raise ValueError("未登录，无法自动获取发送者mid，请指定 sender_uid 参数")

        # 设备id(这个参数我大号是B182F410-3865-46ED-840F-B58B71A78B5E，小号是281ED237-9433-4BF5-BECC-D00AC88E69BF，
        # 但是换过来也能用，估计这个参数不严格)
        dev_id = get_dev_id()
        timestamp = get_timestamp()  # 时间戳（秒）
        data = {
            'msg[sender_uid]': sender_uid,
            'msg[receiver_id]': receiver_uid,
            'msg[receiver_type]': 1,  # 固定为1
            'msg[msg_type]': msg_type,
            'msg[msg_status]': 0,  # 固定为0
            'msg[content]': json.dumps({"content": content}),  # 使用 json.dumps() 将内容转换为 JSON 格式字符串
            'msg[timestamp]': timestamp,
            'msg[dev_id]': dev_id,
            'csrf': BiliCookies.from_file().bili_jct or "",
        }
        return self.session.post(MessageUrls.SEND_MSG, data=data)

    # ---- 读取私信 ----

    @staticmethod
    def _normalize_groups(groups) -> tuple[int, ...]:
        """把分组参数规范化为去重后的 session_type 元组。

        接受 session_type 整数（见 ``MESSAGE_GROUP_NAMES``）或常用名称；
        None 表示默认全部分组（不含“所有系统消息”）。
        """
        if groups is None:
            return DEFAULT_MESSAGE_GROUPS
        if isinstance(groups, bool):
            raise ValueError("groups 必须是分组列表")
        if isinstance(groups, (int, str)):
            groups = [groups]
        elif isinstance(groups, (set, frozenset)):
            groups = sorted(groups)
        if not isinstance(groups, (list, tuple)):
            raise ValueError("groups 必须是分组列表")

        normalized: list[int] = []
        for group in groups:
            if isinstance(group, bool):
                raise ValueError(f"未知私信分组：{group!r}")
            if isinstance(group, int):
                value = group
            elif isinstance(group, str):
                key = group.strip().lower()
                value = int(key) if key.isdigit() else _GROUP_ALIASES.get(key)
            else:
                value = None
            if value not in ALL_MESSAGE_GROUPS:
                raise ValueError(
                    f"未知私信分组：{group!r}；可用分组：{MESSAGE_GROUP_NAMES}"
                )
            if value not in normalized:
                normalized.append(value)
        return tuple(normalized)

    @staticmethod
    def _validate_mid(mid) -> int:
        if isinstance(mid, bool):
            raise ValueError("mid 必须是正整数")
        try:
            value = int(mid)
        except (TypeError, ValueError) as exc:
            raise ValueError("mid 必须是正整数") from exc
        if value <= 0:
            raise ValueError("mid 必须是正整数")
        return value

    @staticmethod
    def _sleep(seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)

    def _get_session_page(self, group: int, end_ts: Optional[int] = None) -> dict:
        params = {
            "session_type": group,
            "group_fold": 0,
            "unfollow_fold": 0,
            "size": _SESSION_PAGE_SIZE,
            "build": 0,
            "mobi_app": "web",
        }
        if group not in (4, 7):
            params["sort_rule"] = 2
        if end_ts:
            params["end_ts"] = end_ts
        return self.session.get(MessageUrls.GET_SESSIONS, params=params)

    def _collect_conversations(self, groups: tuple[int, ...], max_num: int,
                               request_interval: float) -> tuple[list[dict], bool]:
        """按分组收集会话并按最近活跃排序；返回 (会话列表, 是否被 max_num 截断)。"""
        if max_num < -1:
            raise ValueError("max_num 只能为 -1 或非负整数")
        if request_interval < 0:
            raise ValueError("request_interval 不能为负数")
        if max_num == 0 or not groups:
            return [], False

        include_system = 7 in groups
        requested = set(groups)
        # 实测 session_type=7 可能返回空，纯系统会话实际混在 1/9 中
        # （system_msg_type != 0）。显式请求系统消息时补查 1/9，只取系统项。
        query_groups = list(groups)
        if include_system:
            for extra in (1, 9):
                if extra not in query_groups:
                    query_groups.append(extra)
        collected: dict[tuple[int, int], dict] = {}
        stopped_early = False

        for group in query_groups:
            system_only = include_system and group not in requested
            end_ts: Optional[int] = None
            eligible_in_group = 0
            while True:
                try:
                    data = self._get_session_page(group, end_ts=end_ts)
                except BiliAPIError as exc:
                    # 单个分类不可用（如没有花火商单权限）时跳过，不影响其余分组。
                    logger.warning("[MessageService] 获取分组 %s 的会话失败：%s", group, exc)
                    break

                page = data.get("session_list") or []
                new_eligible = 0
                for session in page:
                    if not isinstance(session, dict):
                        continue
                    is_system = bool(_to_int(session.get("system_msg_type")))
                    if system_only and not is_system:
                        continue
                    if not include_system and is_system:
                        continue
                    talker_id = _to_int(session.get("talker_id"))
                    session_type = _to_int(session.get("session_type")) or 1
                    if talker_id <= 0:
                        continue
                    key = (talker_id, session_type)
                    if key in collected:
                        continue
                    collected[key] = session
                    new_eligible += 1
                eligible_in_group += new_eligible

                # 每个分类最多只需要前 max_num 个（按会话时间倒序），
                # 更多会话不可能进入全局前 max_num。
                if max_num >= 0 and eligible_in_group >= max_num:
                    if data.get("has_more") or len(page) > new_eligible:
                        stopped_early = True
                    break
                if not data.get("has_more") or not page:
                    break

                last_ts = min(
                    (ts for ts in (
                        _to_int(session.get("session_ts")) for session in page
                        if isinstance(session, dict)
                    ) if ts > 0),
                    default=0,
                )
                if last_ts <= 0 or last_ts == end_ts:
                    break
                end_ts = last_ts
                self._sleep(request_interval)

        sessions = list(collected.values())
        sessions.sort(
            key=lambda session: (
                _to_int(session.get("session_ts")),
                _to_int(session.get("max_seqno")),
            ),
            reverse=True,
        )

        truncated = False
        if max_num >= 0:
            if len(sessions) > max_num:
                sessions = sessions[:max_num]
                truncated = True
            elif stopped_early:
                truncated = True
        return sessions, truncated

    def get_conversations(self, groups=None, max_num: int = -1,
                          request_interval: float = _DEFAULT_REQUEST_INTERVAL) -> list[dict]:
        """获取会话列表（按最近活跃倒序）。

        :param groups: 要导出的分组（session_type 或名称）。None 表示除系统消息外的全部分组
        :param max_num: 最多返回多少个会话；-1 表示不限制
        :param request_interval: 翻页间隔（秒）
        :return: 原始会话字典列表（含 talker_id/session_type/session_ts/last_msg 等）
        """
        group_values = self._normalize_groups(groups)
        sessions, _ = self._collect_conversations(group_values, max_num, request_interval)
        return sessions

    def _fetch_message_page(self, talker_id: int, session_type: int, size: int,
                            end_seqno: Optional[int] = None) -> dict:
        params = {
            "talker_id": talker_id,
            "session_type": session_type,
            "size": size,
            "sender_device_id": 1,
            "build": 0,
            "mobi_app": "web",
        }
        if end_seqno is not None:
            params["end_seqno"] = end_seqno
        return self.session.get(MessageUrls.FETCH_SESSION_MSGS, params=params)

    def _fetch_messages(self, talker_id: int, session_type: int, page_size: int,
                        request_interval: float) -> list[dict]:
        """拉取一个会话的全部历史消息，返回按时间正序去重后的列表。"""
        if page_size <= 0:
            raise ValueError("page_size 必须为正数")
        request_size = min(page_size, _MAX_MESSAGE_PAGE_SIZE)
        messages: list[dict] = []
        end_seqno: Optional[int] = None

        while True:
            data = self._fetch_message_page(
                talker_id, session_type, request_size, end_seqno=end_seqno
            )
            page = data.get("messages") or []
            messages.extend(page)

            if not data.get("has_more") or not page:
                break
            next_seqno = _to_int(data.get("min_seqno"))
            if next_seqno <= 0 or next_seqno == end_seqno:
                break
            if end_seqno is not None and next_seqno >= end_seqno:
                break
            end_seqno = next_seqno
            self._sleep(request_interval)

        return _sort_messages(messages)

    def _fetch_new_messages(self, talker_id: int, session_type: int,
                            cached_messages: list[dict], page_size: int,
                            request_interval: float) -> tuple[list[dict], int]:
        """从最新一页开始拉取，直到遇到已缓存消息；返回 (合并后消息, 新增数)。"""
        cached_keys = {_message_key(message) for message in cached_messages}
        if not cached_keys:
            messages = self._fetch_messages(
                talker_id, session_type, page_size, request_interval
            )
            return messages, len(messages)

        request_size = min(page_size, _MAX_MESSAGE_PAGE_SIZE)
        fetched: list[dict] = []
        seen_keys: set = set()
        end_seqno: Optional[int] = None

        while True:
            data = self._fetch_message_page(
                talker_id, session_type, request_size, end_seqno=end_seqno
            )
            page = [item for item in (data.get("messages") or []) if isinstance(item, dict)]
            if not page:
                break
            for message in page:
                key = _message_key(message)
                if key not in seen_keys:
                    seen_keys.add(key)
                    fetched.append(message)

            # 该页已与缓存重叠；更早的页必然也在缓存中（缓存是全量同步的）。
            if any(_message_key(message) in cached_keys for message in page):
                break
            if not data.get("has_more"):
                break
            next_seqno = _to_int(data.get("min_seqno"))
            if next_seqno <= 0 or next_seqno == end_seqno:
                break
            if end_seqno is not None and next_seqno >= end_seqno:
                break
            end_seqno = next_seqno
            self._sleep(request_interval)

        merged: dict = {_message_key(message): message for message in cached_messages}
        for message in fetched:
            merged[_message_key(message)] = message
        new_count = len({_message_key(message) for message in fetched} - cached_keys)
        return _sort_messages(list(merged.values())), new_count

    def get_user_messages(self, mid, page_size: int = _DEFAULT_MESSAGE_PAGE_SIZE,
                          request_interval: float = _DEFAULT_REQUEST_INTERVAL) -> list[dict]:
        """获取与指定用户（mid）的全部历史私信，按时间正序返回（不落盘）。"""
        talker_id = self._validate_mid(mid)
        return self._fetch_messages(
            talker_id=talker_id,
            session_type=1,
            page_size=page_size,
            request_interval=request_interval,
        )

    def _fetch_conversations(self, sessions: list[dict], page_size: int,
                             request_interval: float) -> list[dict]:
        """逐会话拉取消息；单个会话业务失败时记录 error 并继续。"""
        conversations: list[dict] = []
        for session in sessions:
            talker_id = _to_int(session.get("talker_id"))
            session_type = _to_int(session.get("session_type")) or 1
            item = {
                "talker_id": talker_id,
                "session_type": session_type,
                "session": session,
                "message_count": 0,
                "messages": [],
                "error": "",
            }
            try:
                item["messages"] = self._fetch_messages(
                    talker_id=talker_id,
                    session_type=session_type,
                    page_size=page_size,
                    request_interval=request_interval,
                )
                item["message_count"] = len(item["messages"])
            except BiliAPIError as exc:
                item["error"] = str(exc)
                logger.warning(
                    "[MessageService] 会话 %s(%s) 获取失败：%s",
                    talker_id, session_type, exc,
                )
            conversations.append(item)
            self._sleep(request_interval)
        return conversations

    def get_all_messages(self, groups=None, max_num: int = -1,
                         page_size: int = _DEFAULT_MESSAGE_PAGE_SIZE,
                         request_interval: float = _DEFAULT_REQUEST_INTERVAL) -> list[dict]:
        """获取最多 max_num 个会话的全部私信（最近活跃优先，不落盘）。

        :param groups: 要导出的分组；None 表示除系统消息外的全部分组
        :param max_num: 最多获取多少个会话；-1 表示不限制
        :param page_size: 单次拉取消息数，最大 2000
        :param request_interval: 翻页间隔（秒）
        :return: ``[{talker_id, session_type, session, message_count, messages, error}]``
        """
        group_values = self._normalize_groups(groups)
        sessions, _ = self._collect_conversations(group_values, max_num, request_interval)
        return self._fetch_conversations(sessions, page_size, request_interval)

    # ---- 导出 / 增量同步 ----

    def _login_account(self) -> tuple[int, str]:
        user = LoginService(self.session).get_login_state()
        if not user.mid:
            raise ValueError("未登录，无法导出私信")
        account_mid = _to_int(user.mid)
        account_name = (user.uname or "").strip() or f"用户{account_mid}"
        return account_mid, account_name

    def _fetch_unames(self, uids) -> dict[int, str]:
        """批量获取用户昵称；失败只记录日志，由调用方回退到缓存或 uid。"""
        unique: list[int] = []
        for value in uids or []:
            uid = _to_int(value)
            if uid > 0 and uid not in unique:
                unique.append(uid)

        names: dict[int, str] = {}
        for start in range(0, len(unique), 100):
            chunk = unique[start:start + 100]
            try:
                data = self.session.get(
                    UserUrls.CARDS,
                    params={"uids": ",".join(str(uid) for uid in chunk)},
                )
            except Exception as exc:
                logger.warning("[MessageService] 获取用户昵称失败：%s", exc)
                continue
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("cards") or data.get("users") or []
            else:
                items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                uid = _to_int(item.get("mid"))
                name = item.get("name")
                if uid > 0 and isinstance(name, str) and name.strip():
                    names[uid] = _sanitize_text(name.strip())
            self._sleep(0.1)
        return names

    def _sync_assets(self, messages: list[dict], friend_dir: Path,
                     assets: dict, force: bool) -> dict:
        """下载消息中的图片到 ``friend_dir/assets``，返回更新后的资源映射。"""
        old_assets = {
            key: value for key, value in (assets or {}).items()
            if isinstance(value, dict)
        }
        effective = {} if force else dict(old_assets)

        http_session = getattr(self.session, "session", None)
        headers = dict(getattr(http_session, "headers", {}) or {})
        headers.setdefault("Referer", "https://www.bilibili.com/")

        for message in messages:
            content = _parse_content(message.get("content"))
            key = _message_key_str(message)
            for index, image in enumerate(_message_images(message)):
                asset_key = f"{key}:{index}"
                current = effective.get(asset_key) or {}
                current_file = current.get("file") or ""
                current_path = friend_dir / current_file if current_file else None

                if (not force and current.get("url") == image["url"] and current_path
                        and current_path.exists() and current_path.stat().st_size > 0):
                    continue

                extension = _image_extension(image["url"], content)
                relative = _asset_relative_path(message, index, extension)
                save_path = friend_dir / relative

                # 无资源映射但同名文件已存在时直接复用，避免重复下载。
                if (not force and not current and save_path.exists()
                        and save_path.stat().st_size > 0):
                    effective[asset_key] = {"url": image["url"], "file": relative}
                    continue

                try:
                    download_stream(
                        image["url"], save_path, headers=headers, overwrite=force
                    )
                    effective[asset_key] = {"url": image["url"], "file": relative}
                except Exception as exc:
                    logger.warning(
                        "[MessageService] 图片下载失败：%s（%s）", image["url"], exc
                    )
                    fallback = old_assets.get(asset_key) or {}
                    fallback_file = fallback.get("file") or ""
                    if fallback_file and (friend_dir / fallback_file).exists():
                        effective[asset_key] = {"url": image["url"], "file": fallback_file}
                    else:
                        effective[asset_key] = {"url": image["url"], "file": ""}
        return effective

    def _export_conversation(self, account_mid: int, account_name: str,
                             base_dir: Path, talker_id: int, session_type: int,
                             session: Optional[dict], force: bool,
                             page_size: int, request_interval: float,
                             name_cache: Optional[dict[int, str]] = None) -> dict:
        """读取缓存/接口数据，增量合并后写入单个会话目录。"""
        friend_dir = Path(base_dir) / str(account_mid) / str(talker_id)
        cached_messages, cached_assets, cached_session, cached_names = (
            _load_conversation_cache(friend_dir, account_mid, talker_id, session_type)
        )
        actual_session = session if session is not None else cached_session

        if force or not cached_messages:
            messages = self._fetch_messages(
                talker_id, session_type, page_size, request_interval
            )
            new_message_count = len(messages)
            assets = {}
        else:
            messages, new_message_count = self._fetch_new_messages(
                talker_id, session_type, cached_messages, page_size, request_interval
            )
            assets = cached_assets

        system_session = bool(_to_int((actual_session or {}).get("system_msg_type")))
        required_uids: set[int] = set()
        if not system_session:
            for message in messages:
                uid = _to_int(message.get("sender_uid"))
                if uid > 0 and uid != account_mid:
                    required_uids.add(uid)
            if session_type == 1 and talker_id > 0:
                required_uids.add(talker_id)

        names = dict(cached_names)
        if name_cache:
            names.update({uid: name for uid, name in name_cache.items() if name})
        to_fetch = [
            uid for uid in required_uids
            if uid not in (name_cache or {})
        ]
        if to_fetch:
            fetched_names = self._fetch_unames(to_fetch)
            names.update(fetched_names)
            if name_cache is not None:
                name_cache.update(fetched_names)

        assets = self._sync_assets(messages, friend_dir, assets, force)
        exported_at = _now_text()
        payload = {
            "version": 2,
            "account_mid": account_mid,
            "account_name": account_name,
            "talker_id": talker_id,
            "session_type": session_type,
            "exported_at": exported_at,
            "message_count": len(messages),
            "session": actual_session,
            "names": {
                str(uid): names[uid]
                for uid in sorted(required_uids) if names.get(uid)
            },
            "assets": assets,
            "messages": messages,
        }
        markdown = _render_markdown(
            account_mid=account_mid,
            account_name=account_name,
            talker_id=talker_id,
            session_type=session_type,
            session=actual_session,
            messages=messages,
            assets=assets,
            names=names,
            exported_at=exported_at,
        )
        json_path = friend_dir / "messages.json"
        markdown_path = friend_dir / "messages.md"
        _write_text_atomic(
            json_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        )
        _write_text_atomic(markdown_path, markdown)
        return {
            "dir": friend_dir,
            "json_path": json_path,
            "markdown_path": markdown_path,
            "message_count": len(messages),
            "new_message_count": new_message_count,
        }

    @staticmethod
    def _base_dir(save_dir, default_dir: Path) -> Path:
        return Path(save_dir) if save_dir is not None else Path(default_dir)

    def export_user_messages(self, mid, save_dir=None, force: bool = False,
                             page_size: int = _DEFAULT_MESSAGE_PAGE_SIZE,
                             request_interval: float = _DEFAULT_REQUEST_INTERVAL) -> MessageExportResult:
        """导出与指定用户（mid）的全部历史聊天记录，默认增量同步。

        文件落在 ``save_dir/{我的mid}/{mid}/``：messages.json、messages.md
        和 assets/（聊天图片）。已存在 messages.json 时只拉取新增消息并合并；
        ``force=True`` 时忽略缓存，全量重拉并重新下载图片。
        """
        talker_id = self._validate_mid(mid)
        account_mid, account_name = self._login_account()
        base_dir = self._base_dir(save_dir, self.default_dir)
        info = self._export_conversation(
            account_mid=account_mid,
            account_name=account_name,
            base_dir=base_dir,
            talker_id=talker_id,
            session_type=1,
            session=None,
            force=bool(force),
            page_size=page_size,
            request_interval=request_interval,
        )
        return MessageExportResult(
            export_dir=info["dir"],
            conversation_dirs=[info["dir"]],
            json_path=info["json_path"],
            markdown_path=info["markdown_path"],
            conversation_count=1,
            message_count=info["message_count"],
            new_message_count=info["new_message_count"],
            talker_id=talker_id,
            forced=bool(force),
        )

    def export_all_messages(self, groups=None, max_num: int = -1, save_dir=None,
                            force: bool = False,
                            page_size: int = _DEFAULT_MESSAGE_PAGE_SIZE,
                            request_interval: float = _DEFAULT_REQUEST_INTERVAL,
                            progress=None,
                            progress_cb: Optional[Callable[[int, int, int, int], None]] = None,
                            display_progress: bool = True) -> MessageExportResult:
        """导出全部私信（或指定分组），每个会话写入独立的 ``{好友mid}`` 目录。

        ``max_num`` 限制会话数量（-1 表示全部），每个会话仍导出全部历史消息。
        默认增量同步；force=True 时对每个会话全量重拉并重新下载资源。

        默认每处理完一个会话刷新一行：
        ``已导出 20 个会话 / 共 100 个会话 / 3200 条消息``。
        ``progress`` 可传入自定义进度对象（需提供 update/finish）；
        ``progress_cb(exported, total, message_count, failed)`` 会在每个会话后调用。
        """
        account_mid, account_name = self._login_account()
        group_values = self._normalize_groups(groups)
        sessions, truncated = self._collect_conversations(
            group_values, max_num, request_interval
        )
        total = len(sessions)
        if progress is None:
            progress = MessageExportProgress(total=total, display=display_progress)
        base_dir = self._base_dir(save_dir, self.default_dir)
        conversation_dirs: list[Path] = []
        errors: list[str] = []
        message_count = 0
        new_message_count = 0
        exported = 0
        failed = 0

        progress.update(0, 0, 0)

        # 私聊对象的昵称一次性批量取回，避免逐个会话重复请求。
        peer_uids = [
            _to_int(session.get("talker_id"))
            for session in sessions
            if (_to_int(session.get("session_type")) or 1) == 1
        ]
        name_cache = self._fetch_unames(peer_uids) if peer_uids else {}

        try:
            for session in sessions:
                talker_id = _to_int(session.get("talker_id"))
                session_type = _to_int(session.get("session_type")) or 1
                try:
                    info = self._export_conversation(
                        account_mid=account_mid,
                        account_name=account_name,
                        base_dir=base_dir,
                        talker_id=talker_id,
                        session_type=session_type,
                        session=session,
                        force=bool(force),
                        page_size=page_size,
                        request_interval=request_interval,
                        name_cache=name_cache,
                    )
                except BiliAPIError as exc:
                    failed += 1
                    summary = f"{talker_id}({session_type}): {exc}"
                    errors.append(summary)
                    logger.warning("[MessageService] 会话 %s 导出失败：%s", talker_id, exc)
                else:
                    exported += 1
                    conversation_dirs.append(info["dir"])
                    message_count += info["message_count"]
                    new_message_count += info["new_message_count"]
                finally:
                    progress.update(exported, message_count, failed)
                    if progress_cb is not None:
                        progress_cb(exported, total, message_count, failed)
                self._sleep(request_interval)
        finally:
            progress.finish()

        return MessageExportResult(
            export_dir=base_dir / str(account_mid),
            conversation_dirs=conversation_dirs,
            conversation_count=exported,
            message_count=message_count,
            new_message_count=new_message_count,
            truncated=truncated,
            forced=bool(force),
            errors=errors,
        )

    def export_messages(self, mid=None, groups=None, max_num: int = -1, save_dir=None,
                        force: bool = False,
                        page_size: int = _DEFAULT_MESSAGE_PAGE_SIZE,
                        request_interval: float = _DEFAULT_REQUEST_INTERVAL,
                        progress=None,
                        progress_cb: Optional[Callable[[int, int, int, int], None]] = None,
                        display_progress: bool = True) -> MessageExportResult:
        """统一导出入口：传入 mid 导出单聊；不传 mid 导出全部会话。

        mid 非空时忽略 groups/max_num（单聊没有分组和会话数概念）。
        progress/progress_cb/display_progress 仅在全部导出时生效。
        """
        if mid is not None:
            return self.export_user_messages(
                mid=mid,
                save_dir=save_dir,
                force=force,
                page_size=page_size,
                request_interval=request_interval,
            )
        return self.export_all_messages(
            groups=groups,
            max_num=max_num,
            save_dir=save_dir,
            force=force,
            page_size=page_size,
            request_interval=request_interval,
            progress=progress,
            progress_cb=progress_cb,
            display_progress=display_progress,
        )
