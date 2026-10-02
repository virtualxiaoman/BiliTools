"""
动态解析层：把接口原始数据解析为稳定的数据模型（纯解析，不访问网络/磁盘）。

[作用] 判断"这条动态是什么、有哪些内容与媒体"，是动态采集工作流的第 1 步。
[输入] detail/feed 接口的 ``item`` 字典；``opus/detail`` 接口的 ``paragraphs`` 列表。
[输出] ``DynamicInfo``（正文块/图片/表情/卡片/转发树/评论定位）与
       ``(blocks, 纯文本, 表情列表)`` 三元组。
[工作流位置] DynamicService.fetch_detail / apply_full_content → 本模块解析 →
             下载（download_dynamic / download_user_dynamics）、渲染
             （dynamic_render）与列表过滤都消费本模块的输出；整体流程见
             src/services/dynamic.py 的模块文档。
"""

import json
from typing import Any, Optional

from src.models.dynamic_model import (
    DynamicAuthor,
    DynamicCard,
    DynamicEmoji,
    DynamicForward,
    DynamicImage,
    DynamicInfo,
    DynamicStats,
    DynamicTopic,
)

_RICH_PREFIX = "RICH_TEXT_NODE_TYPE_"

# major 联合体中除正文/图片外的卡片键（按此顺序构造 DynamicCard）
_CARD_KEYS = (
    "archive", "article", "music", "medialist", "ugc_season",
    "live", "live_rcmd", "pgc", "courses", "common",
    "subscription", "subscription_new",
)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _first_str(raw: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_url(value: Any) -> str:
    """协议相对链接（//www.bilibili.com/...）补全为 https。"""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if text.startswith("//"):
        return "https:" + text
    return text


def _try_json(value: Any) -> Any:
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except ValueError:
            return None
    return None


class DynamicParser:
    """动态解析器：方法均为纯解析（无网络/磁盘副作用），由 DynamicService 调用。"""

    @classmethod
    def parse_item(cls, item: dict, depth: int = 0) -> DynamicInfo:
        """把 detail/feed 的 ``item`` 节点解析为 :class:`DynamicInfo`。

        输入：接口原始 ``item``（含 ``type/basic/modules``）。
        输出：归一化结果——kind（word/draw/forward/archive...）、作者、正文
        blocks、图片/表情、卡片、抽奖 rid、评论定位（comment_oid/comment_type）、
        转发树（嵌套解析 ``orig``）；``info.raw`` 保留原始 item 供 raw.json 存档。

        ``depth`` 为转发递归层数，最大解析 3 层（更深的内容保留 id/作者后截断）。
        """
        if not isinstance(item, dict):
            raise ValueError("动态 item 必须是字典")
        info = DynamicInfo()
        info.raw = item
        info.id = _to_int(item.get("id_str"))
        info.type = str(item.get("type") or "")
        if info.id:
            info.url = f"https://www.bilibili.com/opus/{info.id}"

        modules = item.get("modules") if isinstance(item.get("modules"), dict) else {}
        info.author = cls._parse_author(modules.get("module_author"))
        info.stats = cls._parse_stats(modules.get("module_stat"))

        basic = item.get("basic") if isinstance(item.get("basic"), dict) else {}
        info.comment_oid = _to_int(basic.get("comment_id_str") or basic.get("comment_id"))
        info.comment_type = _to_int(basic.get("comment_type"))

        module_dynamic = modules.get("module_dynamic") if isinstance(modules.get("module_dynamic"), dict) else {}
        info.topic = cls._parse_topic(module_dynamic.get("topic"))
        additional = module_dynamic.get("additional")
        info.additional = additional if isinstance(additional, dict) else {}
        vote = info.additional.get("vote")
        info.vote = vote if isinstance(vote, dict) else None
        major = module_dynamic.get("major") if isinstance(module_dynamic.get("major"), dict) else {}

        # 正文：新式 opus.summary 优先，老式 desc 兜底
        opus = major.get("opus") if isinstance(major.get("opus"), dict) else None
        if opus is not None and isinstance(opus.get("summary"), dict):
            cls._apply_content(info, opus["summary"], str(opus.get("title") or "").strip())
        elif isinstance(module_dynamic.get("desc"), dict):
            cls._apply_content(info, module_dynamic["desc"], "")

        # 图片：opus.pics 或老式 major.draw.items
        pics = opus.get("pics") if opus is not None else None
        if not isinstance(pics, list) and isinstance(major.get("draw"), dict):
            pics = major["draw"].get("items")
        info.images = cls._parse_images(pics)

        info.cards = cls._parse_cards(major, info.additional)

        # 抽奖：正文节点 rid 优先，充电抽奖卡兜底
        for block in info.content.blocks:
            if block.get("type") == "lottery" and block.get("rid"):
                info.lottery_rid = str(block["rid"])
                break
        if not info.lottery_rid:
            lottery = info.additional.get("upower_lottery")
            if isinstance(lottery, dict):
                info.lottery_rid = str(lottery.get("lottery_id") or lottery.get("id") or "")

        # 类型与转发
        if item.get("orig") is not None or info.type == "DYNAMIC_TYPE_FORWARD":
            info.kind = "forward"
        else:
            info.kind = cls._detect_kind(info.type, major)
        if isinstance(item.get("orig"), dict):
            info.forward = cls._parse_forward(item["orig"], depth)
        return info

    @classmethod
    def _apply_content(cls, info: DynamicInfo, container: dict, title: str) -> None:
        """从 desc/summary 容器解析正文块；节点为空时回退到纯文本。"""
        nodes = container.get("rich_text_nodes")
        blocks: list[dict] = []
        if isinstance(nodes, list) and nodes:
            for node in nodes:
                block = cls._node_to_block(node)
                if block is not None:
                    blocks.append(block)
            text = "".join(
                str(node.get("text") or "")
                for node in nodes
                if isinstance(node, dict)
            )
        else:
            text = str(container.get("text") or "")
            if text:
                blocks.append({"type": "text", "text": text})
        info.content.title = title or info.content.title
        info.content.blocks = blocks
        info.content.text = text
        info.content.truncated = bool(container.get("has_more"))
        cls.merge_emojis(info, cls._collect_emojis(blocks))

    @classmethod
    def _node_to_block(cls, node: Any) -> Optional[dict]:
        """富文本节点 → blocks 契约（text/mention/emoji/topic/link/lottery/vote/goods/video/unknown）。"""
        if not isinstance(node, dict):
            return None
        node_type = str(node.get("type") or "")
        suffix = node_type[len(_RICH_PREFIX):] if node_type.startswith(_RICH_PREFIX) else node_type
        text = str(node.get("text") or "")
        jump = _normalize_url(node.get("jump_url"))
        if suffix in ("", "TEXT"):
            return {"type": "text", "text": text}
        if suffix == "AT":
            return {"type": "mention", "text": text, "mid": _to_int(node.get("rid")), "url": jump}
        if suffix == "EMOJI":
            emoji = node.get("emoji") if isinstance(node.get("emoji"), dict) else {}
            return {
                "type": "emoji",
                "text": text,
                "package_id": str(emoji.get("package_id") or ""),
                "emoji_id": str(emoji.get("id") or ""),
                "name": cls.emoji_short_name(str(emoji.get("text") or text)),
                "url": cls._pick_emoji_url(emoji),
            }
        if suffix == "TOPIC":
            return {"type": "topic", "text": text, "url": jump}
        if suffix == "WEB":
            return {"type": "link", "text": text, "url": jump}
        if suffix == "LOTTERY":
            return {"type": "lottery", "text": text, "rid": str(node.get("rid") or ""), "url": jump}
        if suffix == "VOTE":
            return {"type": "vote", "text": text, "rid": str(node.get("rid") or ""), "url": jump}
        if suffix == "GOODS":
            return {"type": "goods", "text": text, "url": jump, "goods": node.get("goods")}
        if suffix in ("BV", "AV", "VIDEO"):
            return {"type": "video", "text": text, "url": jump, "video": node.get("video")}
        return {"type": "unknown", "text": text, "url": jump, "node_type": node_type}

    @staticmethod
    def emoji_short_name(text: str) -> str:
        """从表情节点文本提取短名：``[洛天依…动态表情包_送花]`` → ``送花``；``[doge]`` → ``doge``。"""
        name = str(text or "").strip()
        if name.startswith("[") and name.endswith("]"):
            name = name[1:-1]
        name = name.rsplit("_", 1)[-1].strip()
        return name or "emoji"

    @staticmethod
    def _pick_emoji_url(emoji: dict) -> str:
        """动态表情优先 GIF（保留动画），回退 webp / 静态图。"""
        for key in ("gif_url", "webp_url", "icon_url"):
            value = emoji.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @classmethod
    def _collect_emojis(cls, blocks: list[dict]) -> list[DynamicEmoji]:
        """从 blocks 中收集表情（同包同 id / 同 url 去重，保持出现顺序）。"""
        emojis: list[DynamicEmoji] = []
        seen: set = set()
        for block in blocks:
            if block.get("type") != "emoji":
                continue
            url = str(block.get("url") or "")
            key = (block.get("package_id") or "", block.get("emoji_id") or url)
            if not url or key in seen:
                continue
            seen.add(key)
            emojis.append(DynamicEmoji(
                text=str(block.get("text") or ""),
                package_id=str(block.get("package_id") or ""),
                emoji_id=str(block.get("emoji_id") or ""),
                url=url,
                short_name=str(block.get("name") or cls.emoji_short_name(str(block.get("text") or ""))),
            ))
        return emojis

    @staticmethod
    def merge_emojis(info: DynamicInfo, emojis: list[DynamicEmoji]) -> None:
        """把表情并入 ``info.emojis``（按"包 id + 表情 id/URL"去重，保持出现顺序）。"""
        seen = {(emoji.package_id, emoji.emoji_id or emoji.url) for emoji in info.emojis}
        for emoji in emojis:
            key = (emoji.package_id, emoji.emoji_id or emoji.url)
            if key not in seen:
                seen.add(key)
                info.emojis.append(emoji)

    @staticmethod
    def _parse_images(pics: Any) -> list[DynamicImage]:
        """解析 opus.pics / major.draw.items（两者字段名不同，统一归一化）。"""
        images: list[DynamicImage] = []
        if not isinstance(pics, list):
            return images
        for pic in pics:
            if not isinstance(pic, dict):
                continue
            url = _first_str(pic, ("url", "src"))
            if not url:
                continue
            images.append(DynamicImage(
                index=len(images) + 1,
                url=url,
                width=_to_int(pic.get("width")),
                height=_to_int(pic.get("height")),
                size_kb=float(pic.get("size") or 0.0),
                live_url=str(pic.get("live_url") or ""),
                aigc=_to_int(pic.get("aigc")),
            ))
        return images

    @staticmethod
    def _detect_kind(item_type: str, major: dict) -> str:
        """归一化动态类型（word/draw/article/archive/live/pgc...）。

        输入：接口 ``type`` 字段 + ``major`` 联合体；输出：供渲染与下载
        策略选择的 kind 字符串（见 DynamicInfo.kind）。
        """
        if isinstance(major.get("opus"), dict):
            opus = major["opus"]
            if item_type == "DYNAMIC_TYPE_ARTICLE":
                return "article"
            if opus.get("pics"):
                return "draw"
            if str(opus.get("title") or "").strip():
                return "article"
            return "word"
        for key in ("draw", "archive", "live_rcmd", "live", "pgc", "courses", "music",
                    "medialist", "ugc_season", "common", "article",
                    "subscription", "subscription_new"):
            if isinstance(major.get(key), dict):
                return "live" if key == "live_rcmd" else key
        fallback = {
            "DYNAMIC_TYPE_WORD": "word",
            "DYNAMIC_TYPE_DRAW": "draw",
            "DYNAMIC_TYPE_AV": "archive",
            "DYNAMIC_TYPE_ARTICLE": "article",
            "DYNAMIC_TYPE_COMMON_SQUARE": "common",
            "DYNAMIC_TYPE_LIVE_RCMD": "live",
            "DYNAMIC_TYPE_PGC": "pgc",
            "DYNAMIC_TYPE_COURSES": "courses",
            "DYNAMIC_TYPE_MUSIC": "music",
            "DYNAMIC_TYPE_MEDIALIST": "medialist",
            "DYNAMIC_TYPE_UGC_SEASON": "ugc_season",
            "DYNAMIC_TYPE_FORWARD": "forward",
        }
        return fallback.get(item_type, "unknown")

    @classmethod
    def _parse_forward(cls, orig: dict, depth: int) -> DynamicForward:
        forward = DynamicForward()
        forward.orig_id = _to_int(orig.get("id_str"))
        modules = orig.get("modules") if isinstance(orig.get("modules"), dict) else {}
        author = modules.get("module_author") if isinstance(modules.get("module_author"), dict) else {}
        forward.orig_mid = _to_int(author.get("mid"))
        orig_type = str(orig.get("type") or "")
        if orig_type == "DYNAMIC_TYPE_DELETED" or not modules or depth >= 3:
            forward.deleted = orig_type == "DYNAMIC_TYPE_DELETED" or not modules
            return forward
        try:
            forward.orig = cls.parse_item(orig, depth + 1)
        except ValueError:
            forward.deleted = True
        return forward

    @staticmethod
    def _parse_author(raw: Any) -> DynamicAuthor:
        author = DynamicAuthor()
        if not isinstance(raw, dict):
            return author
        author.mid = _to_int(raw.get("mid"))
        author.name = str(raw.get("name") or "")
        author.face = str(raw.get("face") or "")
        author.pub_time = str(raw.get("pub_time") or "")
        author.pub_ts = _to_int(raw.get("pub_ts"))
        author.location = str(raw.get("pub_location_text") or "")
        pendant = raw.get("pendant") if isinstance(raw.get("pendant"), dict) else {}
        author.pendant_name = str(pendant.get("name") or "")
        author.pendant_image = str(pendant.get("image") or "")
        author.pendant_image_enhance = str(pendant.get("image_enhance") or "")
        decorate = raw.get("decorate") if isinstance(raw.get("decorate"), dict) else {}
        author.decorate_name = str(decorate.get("name") or "")
        author.decorate_card = str(decorate.get("card_url") or "")
        return author

    @staticmethod
    def _parse_topic(raw: Any) -> Optional[DynamicTopic]:
        if not isinstance(raw, dict) or not raw.get("name"):
            return None
        return DynamicTopic(
            id=_to_int(raw.get("id")),
            name=str(raw.get("name") or ""),
            jump_url=_normalize_url(raw.get("jump_url")),
        )

    @staticmethod
    def _parse_stats(raw: Any) -> DynamicStats:
        stats = DynamicStats()
        if not isinstance(raw, dict):
            return stats
        for key in ("like", "comment", "forward"):
            value = raw.get(key)
            if isinstance(value, dict):
                setattr(stats, key, _to_int(value.get("count")))
        return stats

    @classmethod
    def _parse_cards(cls, major: dict, additional: dict) -> list[DynamicCard]:
        """构造卡片列表：major 卡片（视频/直播/预约等）+ additional 附加卡（商品/投票等）。"""
        cards: list[DynamicCard] = []
        for key in _CARD_KEYS:
            raw = major.get(key)
            if not isinstance(raw, dict):
                continue
            card = DynamicCard(kind=key)
            card.title = _first_str(raw, ("title", "name"))
            card.desc = _first_str(raw, ("desc", "description"))
            card.cover_url = _first_str(raw, ("cover", "pic", "cover_url"))
            card.jump_url = _normalize_url(_first_str(raw, ("jump_url", "url")))
            card.bvid = str(raw.get("bvid") or "")
            card.extra = dict(raw)
            if key == "live_rcmd":
                cls._fill_live_rcmd(card, raw)
            cards.append(card)

        additional_type = str(additional.get("type") or "")
        if additional_type and not additional_type.endswith("_NONE"):
            kind = additional_type.replace("ADDITIONAL_TYPE_", "").lower()
            for name, raw in additional.items():
                if name == "type" or not isinstance(raw, dict):
                    continue
                card = DynamicCard(kind=kind if name != "common" else "common")
                card.extra = dict(raw)
                if name == "goods":
                    card.title = str(raw.get("head_text") or "")
                    items = raw.get("items") if isinstance(raw.get("items"), list) else []
                    card.extra = {
                        "head_text": card.title,
                        "items": [
                            {
                                "name": str(item.get("name") or ""),
                                "price": str(item.get("price") or ""),
                                "cover": str(item.get("cover") or ""),
                                "jump_url": _normalize_url(item.get("jump_url")),
                                "brief": str(item.get("brief") or ""),
                            }
                            for item in items
                            if isinstance(item, dict)
                        ],
                    }
                else:
                    card.title = _first_str(raw, ("title", "head_text", "name"))
                    card.desc = _first_str(raw, ("desc", "description"))
                    card.cover_url = _first_str(raw, ("cover", "pic", "cover_url"))
                    card.jump_url = _normalize_url(_first_str(raw, ("jump_url", "url")))
                cards.append(card)
        return cards

    @staticmethod
    def _fill_live_rcmd(card: DynamicCard, raw: dict) -> None:
        """live_rcmd 的标题/封面在嵌套的 JSON 字符串里（live_play_info）。"""
        parsed = _try_json(raw.get("content"))
        if not isinstance(parsed, dict):
            return
        play_info = parsed.get("live_play_info")
        if isinstance(play_info, dict):
            card.title = card.title or str(play_info.get("title") or "")
            card.cover_url = card.cover_url or str(play_info.get("cover") or "")
            card.jump_url = card.jump_url or _normalize_url(play_info.get("link"))

    # ---- 解析：长文段落（opus/detail） ----

    @classmethod
    def parse_paragraphs(cls, paragraphs: list) -> tuple[list[dict], str, list[DynamicEmoji]]:
        """解析 opus/detail 的段落列表（长文全文）。

        输入：``opus/detail`` 接口 ``MODULE_TYPE_CONTENT`` 的 ``paragraphs``。
        输出：``(blocks, 纯文本, 表情列表)``；blocks 在通用契约基础上增加
        ``heading/list/code/quote/line/image`` 等段落类型，供渲染 md 使用。
        """
        blocks: list[dict] = []
        lines: list[str] = []
        for para in paragraphs:
            if not isinstance(para, dict):
                continue
            plain = cls._paragraph_plain_text(para)
            if para.get("line"):
                blocks.append({"type": "line"})
                lines.append("")
                continue
            if para.get("pic"):
                pics = (para.get("pic") or {}).get("pics") if isinstance(para.get("pic"), dict) else None
                for pic in pics or []:
                    if not isinstance(pic, dict):
                        continue
                    url = _first_str(pic, ("url", "src"))
                    if url:
                        blocks.append({
                            "type": "image",
                            "url": url,
                            "width": _to_int(pic.get("width")),
                            "height": _to_int(pic.get("height")),
                        })
                lines.append("")
                continue
            if para.get("code"):
                blocks.append({"type": "code", "text": plain})
                lines.append(plain)
                continue
            if para.get("blockquote"):
                blocks.append({"type": "quote", "text": plain})
                lines.append(plain)
                continue
            if para.get("heading"):
                blocks.append({"type": "heading", "text": plain})
                lines.append(plain)
                continue
            if para.get("list"):
                blocks.append({"type": "list", "text": plain})
                lines.append(plain)
                continue
            if para.get("link_card"):
                link_card = para.get("link_card") or {}
                blocks.append({
                    "type": "link",
                    "text": str(link_card.get("title") or plain or "链接"),
                    "url": str(link_card.get("jump_url") or ""),
                })
                lines.append(plain)
                continue
            # 普通文本段：逐节点转换
            nodes = ((para.get("text") or {}).get("nodes")) if isinstance(para.get("text"), dict) else None
            if isinstance(nodes, list) and nodes:
                for node in nodes:
                    block = cls._paragraph_node_to_block(node)
                    if block is not None:
                        blocks.append(block)
            elif plain:
                blocks.append({"type": "text", "text": plain})
            lines.append(plain)
        return blocks, "\n".join(lines), cls._collect_emojis(blocks)

    @classmethod
    def _paragraph_node_to_block(cls, node: Any) -> Optional[dict]:
        if not isinstance(node, dict):
            return None
        node_type = str(node.get("type") or "")
        if node_type == "TEXT_NODE_TYPE_WORD":
            word = node.get("word") if isinstance(node.get("word"), dict) else {}
            style = word.get("style") if isinstance(word.get("style"), dict) else {}
            return {
                "type": "text",
                "text": str(word.get("words") or ""),
                "bold": bool(style.get("bold")),
                "italic": bool(style.get("italic")),
            }
        if node_type == "TEXT_NODE_TYPE_RICH":
            return cls._node_to_block(node.get("rich") or {})
        return {"type": "unknown", "text": str(node.get("text") or ""), "node_type": node_type}

    @staticmethod
    def _paragraph_plain_text(para: dict) -> str:
        nodes = ((para.get("text") or {}).get("nodes")) if isinstance(para.get("text"), dict) else None
        parts: list[str] = []
        if isinstance(nodes, list):
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if node.get("type") == "TEXT_NODE_TYPE_WORD":
                    word = node.get("word") if isinstance(node.get("word"), dict) else {}
                    parts.append(str(word.get("words") or ""))
                else:
                    rich = node.get("rich") if isinstance(node.get("rich"), dict) else {}
                    parts.append(str(rich.get("text") or node.get("text") or ""))
        return "".join(parts)

