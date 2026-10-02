"""
动态渲染：把解析结果渲染为 Markdown（主产物）与结构化 JSON。

渲染是纯函数（不访问网络/磁盘），便于单测；路径类字段（``file`` 等）
由下载层回填为"相对动态目录"的 POSIX 路径，渲染时优先使用本地路径、
未回填时回退到远程 URL。

[工作流位置] 下载流程的最后一步（_download_resolved 写盘前）：
- ``render_markdown(info, fetched_at)`` → dynamic.md（人读主产物）；
- ``info_to_dict(info)`` → dynamic.json 的 info 段（下载层再补 download 段）。
转发引用块中的相对路径由下载层回填 ``forward.archive_dir`` 后呈现。
"""

import posixpath
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.models.dynamic_model import DynamicInfo

# 北京时间（动态日期与统计时间戳统一口径）
_BEIJING = timezone(timedelta(hours=8))

# 动态类型 → 展示名
_KIND_LABELS = {
    "word": "纯文字动态",
    "draw": "图文动态",
    "article": "专栏/长文动态",
    "forward": "转发动态",
    "archive": "视频动态",
    "live": "直播动态",
    "pgc": "番剧动态",
    "courses": "课程动态",
    "music": "音频动态",
    "medialist": "合集/收藏夹动态",
    "ugc_season": "合集动态",
    "common": "通用卡片动态",
    "subscription": "订阅动态",
    "unknown": "动态",
}

# 卡片 kind → 展示名
_CARD_LABELS = {
    "archive": "视频",
    "article": "专栏",
    "music": "音频",
    "medialist": "合集/收藏夹",
    "ugc_season": "合集",
    "live": "直播",
    "live_rcmd": "直播",
    "pgc": "番剧",
    "courses": "课程",
    "common": "卡片",
    "goods": "商品",
    "reserve": "直播预约",
    "vote": "投票",
    "ugc": "相关推荐",
    "match": "赛事",
    "upower_lottery": "互动抽奖",
    "subscription": "订阅",
    "subscription_new": "订阅",
}


def _join_rel(base_dir: str, relative: str) -> str:
    """把"相对动态目录"的路径换算为"相对当前动态目录"的路径（POSIX）。"""
    if not base_dir:
        return relative
    if not relative:
        return base_dir
    if relative.startswith(("http://", "https://")):
        return relative
    return posixpath.normpath(posixpath.join(base_dir, relative))


def _media_ref(file: str, url: str) -> str:
    """优先本地文件，其次远程 URL。"""
    return file or url


def render_markdown(info: DynamicInfo, *, fetched_at: Optional[datetime] = None) -> str:
    """把一条动态渲染为 Markdown 文本。

    :param fetched_at: 数据抓取时间（用于"数据统计日期"）。None 时取当前时间；
                       下载流程会传入实际抓取时刻，测试可传固定值保证确定性。
    """
    lines: list[str] = []
    lines.append(f"# {dynamic_title(info)}")
    lines.append("")

    # 元信息（发布时间用 pub_ts 渲染完整日期时间，接口的 pub_time 可能是"9月1日"这类短格式）
    meta = [f"作者：{info.author.name or '未知'} ({info.author.mid})"]
    pub_text = _format_pub_time(info)
    if pub_text:
        meta.append(pub_text)
    meta.append(_type_description(info))
    lines.append("> " + " ｜ ".join(meta))
    if info.url:
        lines.append(f"> 原文：{info.url}")
    if info.topic is not None:
        lines.append(f"> 话题：#{info.topic.name}#")
    if info.author.location:
        lines.append(f"> 地点：{info.author.location}")
    lines.append(
        f"> 数据：点赞 {info.stats.like} · 评论 {info.stats.comment} · 转发 {info.stats.forward}"
    )
    moment = fetched_at if fetched_at is not None else datetime.now(_BEIJING)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_BEIJING)
    lines.append(f"> 数据统计日期是{moment.astimezone(_BEIJING).strftime('%y.%m.%d %H:%M')}")
    if info.content.truncated and not info.content.full_text_fetched:
        lines.append("> 注：正文为摘要，全文见原文链接")
    lines.append("")

    # 正文
    body = _render_blocks(info)
    if body.strip():
        lines.append(body)
        lines.append("")

    # 图片清单（全文模式下图片已内联展示，不重复列出）
    if info.images and not _blocks_have_images(info):
        lines.append(f"## 图片（{len(info.images)}）")
        for image in info.images:
            ref = _media_ref(image.file, image.url)
            alt = f"{image.index:02d}"
            if image.live_file:
                # markdown 标准不支持视频：图片作为兜底展示，同时给出 <video>
                # 标签（支持 HTML 的渲染器可直接播放动态图）
                lines.append(f"![{alt}]({ref})")
                lines.append("")
                lines.append(f'<video src="{image.live_file}" poster="{ref}" controls></video>')
            elif image.live_url:
                lines.append(f"![{alt}]({ref}) （动态图：[视频]({image.live_url})）")
            else:
                lines.append(f"![{alt}]({ref})")
        lines.append("")

    # 卡片
    for card in info.cards:
        lines.extend(_render_card(card))
        lines.append("")

    # 互动抽奖
    if info.lottery_rid:
        lines.append("## 互动抽奖")
        lines.append(f"- 抽奖 ID：{info.lottery_rid}（参与入口见原文链接）")
        lottery = info.additional.get("upower_lottery")
        if isinstance(lottery, dict):
            prize = lottery.get("prize_info")
            if isinstance(prize, dict) and prize.get("prize_name"):
                lines.append(f"- 奖品：{prize.get('prize_name')}")
        lines.append("")

    # 投票
    if info.vote:
        lines.append("## 投票")
        options = info.vote.get("options") or []
        desc = info.vote.get("desc") or ""
        if desc:
            lines.append(f"- 说明：{desc}")
        for option in options:
            if isinstance(option, dict):
                lines.append(f"- {option.get('desc') or option.get('title') or ''}")
        lines.append("")

    # 转发
    if info.kind == "forward" and info.forward is not None:
        lines.extend(_render_forward(info.forward))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def dynamic_title(info: DynamicInfo) -> str:
    """动态标题：优先 opus 标题，其次正文首行（截断 40 字），否则用 ID 兜底。"""
    if info.content.title:
        return info.content.title
    first = (info.content.text or "").strip().splitlines()
    if first and first[0].strip():
        text = first[0].strip()
        return text[:40] + ("…" if len(text) > 40 else "")
    return f"动态 {info.id}"


def _format_pub_time(info: DynamicInfo) -> str:
    """发布时间：优先用 pub_ts 渲染为 `YYYY-MM-DD HH:MM`（北京时间）。

    接口的 ``pub_time`` 对较新的动态可能只给"9月1日"这类短格式（无年份与时分），
    因此渲染展示统一以 ``pub_ts`` 为准，缺失时回退到接口文本。
    """
    if info.author.pub_ts > 0:
        moment = datetime.fromtimestamp(info.author.pub_ts, tz=_BEIJING)
        return moment.strftime("%Y-%m-%d %H:%M")
    return info.author.pub_time


def _type_description(info: DynamicInfo) -> str:
    label = _KIND_LABELS.get(info.kind, "动态")
    extras: list[str] = []
    if info.lottery_rid:
        extras.append("含互动抽奖")
    if info.vote:
        extras.append("含投票")
    if any(card.kind == "goods" for card in info.cards):
        extras.append("含商品")
    if info.content.full_text_fetched:
        extras.append("已取全文")
    return label + (f"（{'、'.join(extras)}）" if extras else "")


def _emoji_map(info: DynamicInfo) -> dict:
    mapping: dict = {}
    for emoji in info.emojis:
        mapping[(emoji.package_id, emoji.emoji_id)] = emoji
    return mapping


def _image_map(info: DynamicInfo) -> dict:
    return {image.url: image for image in info.images}


def _blocks_have_images(info: DynamicInfo) -> bool:
    return any(block.get("type") == "image" for block in info.content.blocks)


def _render_blocks(info: DynamicInfo) -> str:
    emoji_map = _emoji_map(info)
    image_map = _image_map(info)
    paragraph_mode = info.content.full_text_fetched
    parts: list[str] = []
    for block in info.content.blocks:
        if not isinstance(block, dict):
            continue
        rendered = _render_block(block, emoji_map, image_map)
        if rendered is None:
            continue
        if paragraph_mode and parts and not parts[-1].endswith("\n"):
            parts.append("\n")
        parts.append(rendered)
    return "".join(parts).strip("\n")


def _render_block(block: dict, emoji_map: dict, image_map: dict) -> str | None:
    block_type = block.get("type")
    text = str(block.get("text") or "")
    if block_type == "text":
        rendered = text
        if block.get("bold") and text:
            rendered = f"**{text}**"
        if block.get("italic") and text:
            rendered = f"*{text}*"
        return rendered
    if block_type == "mention":
        return text or f"@{block.get('mid', '')}"
    if block_type == "emoji":
        emoji = emoji_map.get((block.get("package_id"), block.get("emoji_id")))
        name = (emoji.short_name if emoji else block.get("name")) or "emoji"
        ref = ""
        if emoji is not None:
            ref = _media_ref(emoji.file, emoji.url)
        ref = ref or str(block.get("url") or "")
        if ref:
            return f"![{name}]({ref})"
        return text or f"[{name}]"
    if block_type == "topic":
        return text
    if block_type == "link":
        url = str(block.get("url") or "")
        label = text if text and text != url else url
        return f"[{label}]({url})" if url else label
    if block_type == "lottery":
        return f"【{text or '互动抽奖'}】"
    if block_type == "vote":
        return f"【{text or '投票'}】"
    if block_type in ("goods", "video"):
        url = str(block.get("url") or "")
        return f"[{text}]({url})" if url and text else (text or url)
    if block_type == "heading":
        return f"### {text}"
    if block_type == "list":
        return f"- {text}"
    if block_type == "quote":
        return "> " + text.replace("\n", "\n> ")
    if block_type == "code":
        return f"```\n{text}\n```"
    if block_type == "line":
        return "---"
    if block_type == "image":
        image = image_map.get(str(block.get("url") or ""))
        if image is not None:
            return f"![{image.index:02d}]({_media_ref(image.file, image.url)})"
        url = str(block.get("url") or "")
        return f"![]({url})" if url else None
    return text or None


def _render_card(card) -> list[str]:
    label = _CARD_LABELS.get(card.kind, card.kind)
    heading = f"## 卡片：{label}"
    if card.bvid:
        heading += f" {card.bvid}"
    lines = [heading]
    if card.kind == "goods":
        items = card.extra.get("items") or []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or "商品"
            price = f" ｜ {item['price']}" if item.get("price") else ""
            lines.append(f"- {name}{price}")
            if item.get("jump_url"):
                lines.append(f"  - 链接：{item['jump_url']}")
            cover_ref = item.get("cover_file") or item.get("cover")
            if cover_ref:
                lines.append(f"  - ![封面]({cover_ref})")
        return lines
    if card.kind == "reserve":
        if card.title:
            lines.append(f"- 标题：{card.title}")
        for key in ("desc1", "desc2", "desc3"):
            desc = card.extra.get(key)
            if isinstance(desc, dict) and desc.get("text"):
                suffix = f"（{desc['jump_url']}）" if desc.get("jump_url") else ""
                lines.append(f"- {desc['text']}{suffix}")
        return lines
    detail: list[str] = []
    if card.title:
        detail.append(f"标题：{card.title}")
    if card.kind != "archive" and card.desc and not card.desc.startswith(card.title):
        detail.append(f"说明：{card.desc}")
    if card.jump_url:
        detail.append(f"链接：{card.jump_url}")
    for item in detail:
        lines.append(f"- {item}")
    if card.cover_file or card.cover_url:
        lines.append(f"![封面]({_media_ref(card.cover_file, card.cover_url)})")
    return lines


def _render_forward(forward) -> list[str]:
    if forward.deleted:
        return ["## 转发", "", "> 原动态已删除"]
    orig = forward.orig
    if orig is None:
        return ["## 转发", "", f"> 原动态内容未展开（超过递归深度，ID：{forward.orig_id}）"]
    author = f"{orig.author.name or '未知'} ({orig.author.mid})"
    lines = [f"## 转发自 {author}"]
    if forward.archive_dir:
        lines.append(f"> 本地存档：{forward.archive_dir}")
    else:
        lines.append(f"> 原文：{orig.url}")
    lines.append("")
    body = _render_blocks(orig)
    if body.strip():
        lines.append("> " + body.replace("\n", "\n> "))
        lines.append("")
    if orig.images:
        lines.append(f"> 原动态图片（{len(orig.images)}）：")
        for image in orig.images:
            ref = _join_rel(forward.archive_dir, image.file) if image.file else image.url
            lines.append(f"> ![原{image.index:02d}]({ref})")
            if image.live_file:
                live_ref = _join_rel(forward.archive_dir, image.live_file)
                lines.append(f'> <video src="{live_ref}" poster="{ref}" controls></video>')
    return lines


def info_to_dict(info: DynamicInfo) -> dict:
    """结构化输出（dynamic.json 的 info 部分；download 段由下载层补充）。"""
    forward = None
    if info.forward is not None:
        forward = {
            "orig_id": info.forward.orig_id,
            "orig_mid": info.forward.orig_mid,
            "deleted": info.forward.deleted,
            "archive_dir": info.forward.archive_dir,
        }
    return {
        "schema_version": 1,
        "id": str(info.id),
        "type": info.type,
        "kind": info.kind,
        "url": info.url,
        "author": {
            "mid": info.author.mid,
            "name": info.author.name,
            "face": info.author.face,
            "pub_time": info.author.pub_time,
            "pub_ts": info.author.pub_ts,
            "location": info.author.location,
        },
        "topic": (
            {"id": info.topic.id, "name": info.topic.name, "jump_url": info.topic.jump_url}
            if info.topic is not None
            else None
        ),
        "content": {
            "title": info.content.title,
            "text": info.content.text,
            "blocks": info.content.blocks,
            "truncated": info.content.truncated,
            "full_text_fetched": info.content.full_text_fetched,
        },
        "media": {
            "images": [
                {
                    "index": image.index,
                    "file": image.file,
                    "live_file": image.live_file,
                    "url": image.url,
                    "width": image.width,
                    "height": image.height,
                    "size_kb": image.size_kb,
                    "live_url": image.live_url,
                    "aigc": image.aigc,
                }
                for image in info.images
            ],
            "emojis": [
                {
                    "file": emoji.file,
                    "package_id": emoji.package_id,
                    "emoji_id": emoji.emoji_id,
                    "text": emoji.text,
                }
                for emoji in info.emojis
            ],
        },
        "cards": [
            {
                "kind": card.kind,
                "title": card.title,
                "desc": card.desc,
                "jump_url": card.jump_url,
                "cover_url": card.cover_url,
                "cover_file": card.cover_file,
                "bvid": card.bvid,
                "extra": card.extra,
            }
            for card in info.cards
        ],
        "lottery": {"rid": info.lottery_rid} if info.lottery_rid else None,
        "vote": info.vote,
        "stats": {
            "like": info.stats.like,
            "comment": info.stats.comment,
            "forward": info.stats.forward,
        },
        "forward": forward,
    }
