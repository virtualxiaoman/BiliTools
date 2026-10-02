"""
动态（opus）服务：详情解析、全文获取与目录化下载。

设计要点（详见 docs/动态下载开发计划.md）：
- detail 接口必须携带 features（DynamicUrls.DETAIL_FEATURES），否则正文与附加卡片丢失；
- 长文 summary.has_more=true 时用 opus/detail 接口取全文（段落化结构）；
- 一条动态 = 一个目录，媒体落在 UP 目录的 `_assets/` 下（编号与账本见 asset_allocator）。
"""

import json
import logging
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

from src.api.auth import get_wbi
from src.api.errors import BiliAPIError, BiliForbiddenError, BiliRiskError
from src.api.session import BiliSession
from src.config.path import DYNAMIC_OUTPUT_DIR
from src.models.download_model import DownloadResult
from src.models.dynamic_model import (
    DynamicAuthor,
    DynamicCard,
    DynamicDownloadResult,
    DynamicEmoji,
    DynamicForward,
    DynamicImage,
    DynamicInfo,
    DynamicStats,
    DynamicTopic,
)
from src.services.dynamic_render import dynamic_title, info_to_dict, render_markdown
from src.services.reply import ReplyService
from src.urls.dynamic_urls import DynamicUrls
from src.util.asset_allocator import AssetIdAllocator, get_asset_allocator
from src.util.downloader import download_stream
from src.util.filename import sanitize_filename
from src.util.progress import BatchProgress, ParallelBatchProgress
from src.util.risk_gate import RiskGate

logger = logging.getLogger(__name__)

# 完成标记：成功写 dynamic_id.txt；媒体最终失败写 dynamic_id_failed.txt（内容均为动态 ID），
# 便于按文件名统计成功/失败数量；两者互斥，重跑成功后会清除失败标记。
_SUCCESS_MARKER = "dynamic_id.txt"
_FAILED_MARKER = "dynamic_id_failed.txt"

# opus 链接：https://www.bilibili.com/opus/<id>（也兼容 m. 域名与结尾斜杠）
_OPUS_PATH_RE = re.compile(r"^/opus/(\d+)/?$")
# 旧分享链：https://t.bilibili.com/<id>
_T_PATH_RE = re.compile(r"^/(\d+)/?$")

_RICH_PREFIX = "RICH_TEXT_NODE_TYPE_"

# 空间动态列表翻页节流：基准间隔（秒）+ 随机抖动比例，避免固定节奏触发风控
_FEED_PAGE_INTERVAL = 1.0
_FEED_PAGE_JITTER_RATIO = 0.5
# 触发风控（-412/-403）后的退避基数（秒），按 2^n 递增并附加随机抖动
_RISK_BACKOFF_BASE = 30.0

# 北京时间（动态日期与爬取进度统一口径）
_BEIJING = timezone(timedelta(hours=8))

# CDN 镜像回退：i0/i1/i2.hdslb.com 互为镜像（i3+ 不存在，不要尝试）
_CDN_HOST_FALLBACKS = ("i2.hdslb.com", "i1.hdslb.com")
_CDN_HOST_RE = re.compile(r"^i(0|1|2)\.hdslb\.com$")

# 列表快照文件名（保存在 `{save_dir}/{mid}/` 下，供复用已爬取的列表）
_LIST_SNAPSHOT_NAME = "dynamic_list.json"

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


def _mirror_urls(url: str) -> list[str]:
    """为 hdslb CDN 资源生成镜像回退顺序：原 host 优先，其后 i2、i1（不使用 i3+）。

    例：``i0.hdslb.com`` 失败后尝试 ``i2.hdslb.com``，再尝试 ``i1.hdslb.com``；
    非 i0/i1/i2 域名的 URL 原样返回（不生成回退）。
    """
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if _CDN_HOST_RE.fullmatch(host) is None:
        return [url]
    candidates = [url]
    for fallback in _CDN_HOST_FALLBACKS:
        if fallback == host:
            continue
        candidate = urlunparse(parsed._replace(netloc=fallback))
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _try_json(value: Any) -> Any:
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except ValueError:
            return None
    return None


class DynamicService:
    """B 站动态服务：解析与（后续批次）下载。"""

    def __init__(self, session: Optional[BiliSession] = None, default_dir=None):
        self.session = session if session is not None else BiliSession()
        self.default_dir = Path(default_dir) if default_dir is not None else DYNAMIC_OUTPUT_DIR
        self.reply_service = ReplyService(session=self.session)

    # ---- ID 解析 ----

    @staticmethod
    def resolve_dynamic_id(value: int | str) -> int:
        """从动态 ID、``bilibili.com/opus/<id>`` 或 ``t.bilibili.com/<id>`` 链接中提取动态 ID。"""
        if isinstance(value, bool):
            raise ValueError("dynamic_id 必须是动态 ID 或 opus 链接")
        if isinstance(value, int):
            dynamic_id = value
        elif isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError("dynamic_id 不能为空")
            if text.isdigit():
                dynamic_id = int(text)
            elif "://" in text:
                parsed = urlparse(text)
                host = (parsed.netloc or "").lower()
                match = _OPUS_PATH_RE.fullmatch(parsed.path)
                if match is None and host.endswith("t.bilibili.com"):
                    match = _T_PATH_RE.fullmatch(parsed.path)
                if match is None:
                    raise ValueError("动态链接必须是 https://www.bilibili.com/opus/<id> 或 https://t.bilibili.com/<id>")
                dynamic_id = int(match.group(1))
            else:
                raise ValueError("dynamic_id 必须是正整数、opus 链接或 t.bilibili.com 链接")
        else:
            raise ValueError("dynamic_id 必须是动态 ID 或 opus 链接")
        if dynamic_id <= 0:
            raise ValueError("dynamic_id 必须是正整数")
        return dynamic_id

    # ---- 获取 ----

    def fetch_raw(self, dynamic_id: int | str) -> dict:
        """请求动态详情原始 data（必须带 features，见模块 docstring）。"""
        oid = self.resolve_dynamic_id(dynamic_id)
        return self.session.get(
            DynamicUrls.DETAIL,
            params={"id": oid, "features": DynamicUrls.DETAIL_FEATURES},
        )

    def fetch_detail(self, dynamic_id: int | str, *, full_content: bool = False) -> DynamicInfo:
        """获取并解析一条动态。

        :param full_content: 为 True 且正文被截断（长文/专栏）时，追加请求
                             opus/detail 接口获取全文；失败时保留摘要并记录 warning。
        """
        data = self.fetch_raw(dynamic_id)
        item = data.get("item") if isinstance(data, dict) else None
        if not isinstance(item, dict):
            raise ValueError("动态详情响应缺少 item")
        info = self.parse_item(item)
        if full_content and info.content.truncated:
            try:
                info = self.apply_full_content(info)
            except Exception as exc:  # 全文接口失败不应阻断整体流程
                logger.warning("[DynamicService] 获取全文失败（保留摘要）：%s", exc)
        return info

    def apply_full_content(self, info: DynamicInfo) -> DynamicInfo:
        """用 opus/detail 接口的段落化全文替换 ``info.content``（标题/正文块/纯文本）。"""
        if info.id <= 0:
            return info
        data = self.session.get(
            DynamicUrls.OPUS_DETAIL,
            params={"id": info.id, "timezone_offset": -480},
        )
        item = data.get("item") if isinstance(data, dict) else None
        modules = item.get("modules") if isinstance(item, dict) else None
        if not isinstance(modules, list):
            return info
        title = info.content.title
        paragraphs: list = []
        for module in modules:
            if not isinstance(module, dict):
                continue
            if module.get("module_type") == "MODULE_TYPE_TITLE":
                module_title = module.get("module_title") or {}
                title = str(module_title.get("text") or "").strip() or title
            elif module.get("module_type") == "MODULE_TYPE_CONTENT":
                content = module.get("module_content") or {}
                value = content.get("paragraphs")
                if isinstance(value, list):
                    paragraphs = value
        if not paragraphs:
            return info
        blocks, text, emojis = self.parse_paragraphs(paragraphs)
        info.content.title = title
        info.content.blocks = blocks
        info.content.text = text
        info.content.full_text_fetched = True
        self._merge_emojis(info, emojis)
        return info

    # ---- 解析：动态 item ----

    @classmethod
    def parse_item(cls, item: dict, depth: int = 0) -> DynamicInfo:
        """把 detail/feed 的 ``item`` 节点解析为 :class:`DynamicInfo`。

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
        cls._merge_emojis(info, cls._collect_emojis(blocks))

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
    def _merge_emojis(info: DynamicInfo, emojis: list[DynamicEmoji]) -> None:
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
        """归一化动态类型（用于渲染与下载策略选择）。"""
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
        """解析 opus/detail 的段落列表。

        :return: (blocks, 纯文本, 表情列表)；blocks 在通用契约基础上增加
                 ``heading/list/code/quote/line/image`` 等段落类型。
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

    # ---- 下载 ----

    def download_dynamic(
        self,
        dynamic_id: int | str,
        *,
        save_dir=None,
        force: bool = False,
        with_comments: bool = True,
        comment_max_count: int = 20,
        comment_sort: str = "hot",
        max_forward_depth: int = 3,
        progress=None,
        progress_cb=None,
    ) -> DynamicDownloadResult:
        """下载一条动态到目录化结构（含转发递归与评论存档）。

        目录规则：``{save_dir}/{mid}/{YYYY-MM}/{YYYY-MM-DD}_{当天序号}/``，
        媒体落在 ``{save_dir}/{mid}/_assets/``（图片/封面经账本取号，
        头像/表情按 manifest 缓存）；``dynamic_id.txt`` 最后写入，作为完成标记。

        :param save_dir: 输出根目录，默认 ``output/dynamic``
        :param force: True 时动态内容与 _assets 全部重下（复用账本原文件名覆盖）
        :param with_comments: 是否抓取评论存档（默认前 20 条热评）
        :param comment_max_count: 评论条数上限；-1 表示全部
        :param comment_sort: ``hot``（最热）或 ``latest``（最新）
        :param max_forward_depth: 转发递归最大深度（防循环）
        :param progress: 复用外部进度对象（BatchProgress/ParallelBatchProgress）
        :param progress_cb: 每个媒体文件完成后的回调 ``(done, total)``
        """
        if max_forward_depth < 0:
            raise ValueError("max_forward_depth 不能为负数")
        info = self.fetch_detail(dynamic_id, full_content=True)
        root = Path(save_dir) if save_dir is not None else self.default_dir
        return self._download_resolved(
            info,
            root,
            force=force,
            with_comments=with_comments,
            comment_max_count=comment_max_count,
            comment_sort=comment_sort,
            max_forward_depth=max_forward_depth,
            depth=0,
            ancestors=(),
            progress=progress,
            progress_cb=progress_cb,
        )

    # ---- 批量：UP 主全部动态 ----

    @staticmethod
    def normalize_mid(mid: int | str) -> int:
        """规范化 mid（后端只接收 int 或纯数字字符串，URL 由前端归一化）。"""
        if mid is None or isinstance(mid, bool):
            raise ValueError("需要提供 mid")
        text = str(mid).strip()
        if not text.isdigit():
            raise ValueError(f"mid 必须是纯数字，收到：{mid}")
        value = int(text)
        if value <= 0:
            raise ValueError("mid 必须是正整数")
        return value

    @staticmethod
    def _parse_since(since) -> Optional[int]:
        """把 since 归一化为"北京时间当天 0 点"的 unix 时间戳；None 表示不限制。"""
        if since is None:
            return None
        if isinstance(since, bool):
            raise ValueError("since 必须是 YYYY-MM-DD、时间戳或 datetime")
        if isinstance(since, (int, float)):
            return int(since)
        if isinstance(since, datetime):
            moment = since
        elif isinstance(since, date):
            moment = datetime(since.year, since.month, since.day)
        elif isinstance(since, str):
            match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", since.strip())
            if match is None:
                raise ValueError("since 必须是 YYYY-MM-DD 或时间戳")
            moment = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        else:
            raise ValueError("since 必须是 YYYY-MM-DD、时间戳或 datetime")
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=_BEIJING)
        return int(moment.timestamp())

    def list_user_dynamics(
        self,
        mid: int | str,
        *,
        max_count: int = -1,
        since=None,
        page_interval: float = _FEED_PAGE_INTERVAL,
        display: bool = True,
        progress_cb=None,
        risk_gate: Optional[RiskGate] = None,
        risk_retries: int = 3,
        use_cache: bool = True,
        save_snapshot: bool = True,
        save_dir=None,
        captcha_handler=None,
        captcha_wait: bool = True,
    ) -> list[dict]:
        """翻页获取 UP 主空间的动态 item 列表（时间倒序，按 id 去重）。

        防風控：页间默认间隔 1 秒并叠加随机抖动（``page_interval`` 可调）；
        单页触发 -412/-403 时按指数退避自动重试（次数由 ``risk_retries`` 控制），
        仍失败抛 ``BiliRiskError``；触发 **-352（风控验证）时暂停**等待用户在
        浏览器完成验证码（``captcha_handler`` 或控制台输入 y），完成后继续爬取。

        列表快照：**全量请求**（不限条数/日期）会把结果保存在
        ``{save_dir}/{mid}/dynamic_list.json``。快照是连续的一段历史区间，
        下次默认读取它做**增量刷新**：① 从最新处爬到与快照重叠（获取新动态）；
        ② 若上次快照未爬完，再从快照最旧一条之后继续向更早翻页；
        ③ 合并保存。``use_cache=False`` 表示忽略快照、完整重爬。

        [使用方法]
            service = DynamicService()
            items = service.list_user_dynamics(36081646, max_count=20)
            items = service.list_user_dynamics(36081646, since="2026-09-01")
            service.list_user_dynamics(36081646, page_interval=2.0)  # 更保守的爬取节奏
            service.list_user_dynamics(36081646, use_cache=False)   # 忽略快照，完整重爬

        :param mid: UP 主 mid（int 或纯数字字符串）
        :param max_count: 最多返回多少条（-1 表示翻到底；非 -1 时不做快照读写）
        :param since: 只保留该日期（含当天，北京时间）之后发布的动态；
                      YYYY-MM-DD 字符串、时间戳或 datetime 均可
        :param page_interval: 翻页间隔基准秒数（默认 1.0，附加最多 50% 随机抖动；
                              0 表示不等待，仅测试用）
        :param display: 未提供 ``progress_cb`` 时，是否在控制台逐页打印爬取进度
        :param progress_cb: 每页完成后的回调 ``(page, items_found)``
        :param risk_gate: 可选的风控协调器（多线程场景共享；默认内部新建）
        :param risk_retries: 单页触发风控的最大重试次数（默认 3）
        :param use_cache: 是否读取已保存的列表快照做增量刷新（默认 True）
        :param save_snapshot: 全量请求完成后是否保存列表快照（默认 True）
        :param save_dir: 快照所在的输出根目录，默认 ``output/dynamic``
        :param captcha_handler: -352 时的替代交互回调 ``(message) -> bool``：
                                True 继续、False 放弃；提供时不走控制台输入
        :param captcha_wait: 触发 -352 时是否在控制台暂停等待用户完成验证码（默认 True）
        :return: 接口 ``items`` 原始字典列表；置顶动态按真实发布日期参与过滤
        """
        if max_count < -1:
            raise ValueError("max_count 只能为 -1 或非负整数")
        if page_interval < 0:
            raise ValueError("page_interval 不能为负数")
        if risk_retries < 0:
            raise ValueError("risk_retries 不能为负数")
        uid = self.normalize_mid(mid)
        since_ts = self._parse_since(since)
        options = _CrawlOptions(
            gate=risk_gate if risk_gate is not None else RiskGate(),
            risk_retries=risk_retries,
            page_interval=page_interval,
            captcha_handler=captcha_handler,
            captcha_wait=captcha_wait,
            display=display,
            progress_cb=progress_cb,
        )
        # 快照只服务于"全量请求"（不限条数/日期）；快照 = 连续的一段历史区间 [最旧..最新]：
        # 增量刷新 = 从最新爬到与快照重叠（拿新动态）+ 若快照未爬完，跳到其最旧一条继续向更早翻。
        full_request = max_count < 0 and since is None
        cached_items: list = []
        cached_meta: dict = {}
        if full_request and use_cache:
            cached_items, cached_meta = self._load_list_snapshot(uid, save_dir=save_dir)

        top_items: list = []
        deep_items: list = []
        known_ids: set = set()
        hit_cache = False
        result = "exhausted"
        try:
            if cached_items:
                cached_ids = {
                    str(item.get("id_str"))
                    for item in cached_items
                    if item.get("id_str")
                }
                known_ids |= cached_ids
                if display:
                    state = "完整" if cached_meta.get("complete") else "未爬完"
                    print(
                        f"\n[列表缓存] 已读取 {len(cached_items)} 条"
                        f"（抓取于 {cached_meta.get('fetched_at') or '未知'}，{state}），从最新处增量补齐；"
                        "如需完整重爬请传 use_cache=False"
                    )
                result = self._crawl_pages(
                    uid, options=options, collected=top_items, known_ids=known_ids,
                    stop_ids=cached_ids, base_count=len(cached_items),
                )
                hit_cache = result == "hit"
                if hit_cache and not cached_meta.get("complete"):
                    oldest_id = str(cached_items[-1].get("id_str") or "")
                    if oldest_id:
                        if display:
                            print("\n[列表缓存] 快照未爬完：跳过已覆盖区间，继续向更早翻页…")
                        result = self._crawl_pages(
                            uid, options=options, collected=deep_items, known_ids=known_ids,
                            start_offset=oldest_id,
                            base_count=len(cached_items) + len(top_items),
                        )
            else:
                result = self._crawl_pages(
                    uid, options=options, collected=top_items, known_ids=known_ids,
                    max_count=max_count, since_ts=since_ts,
                )
        except Exception:
            # 中断也保存已获取的部分（标记未完成），下次运行可在此基础上继续补齐
            if full_request and save_snapshot:
                partial = self._merge_items(top_items, cached_items, deep_items)
                if partial:
                    self._save_dynamic_list(uid, partial, save_dir=save_dir, complete=False, display=display)
            raise

        if cached_items and hit_cache:
            items = self._merge_items(top_items, cached_items, deep_items)
            complete = bool(cached_meta.get("complete")) or result == "exhausted"
        else:
            if cached_items:
                logger.warning("[DynamicService] 列表快照与当前空间列表无交集（动态可能已删除），忽略旧快照")
            items = top_items
            complete = result == "exhausted"
        if max_count >= 0:
            items = items[:max_count]
        if options.printed:
            print(f"\r[爬取列表] 完成：共 {len(items)} 条{self._crawl_tail(items)}            ")
        if full_request and save_snapshot and items:
            self._save_dynamic_list(uid, items, save_dir=save_dir, complete=complete, display=display)
        return items

    def _crawl_pages(
        self,
        uid: int,
        *,
        options: "_CrawlOptions",
        collected: list,
        known_ids: set,
        start_offset: str = "",
        stop_ids: Optional[set] = None,
        base_count: int = 0,
        max_count: int = -1,
        since_ts: Optional[int] = None,
    ) -> str:
        """单向翻页收集（从 ``start_offset`` 向旧）。

        :return: ``"hit"``（撞到 ``stop_ids`` 代表的快照区间）、
                 ``"exhausted"``（翻到尽头）、``"stopped"``（达到 max_count / since 提前截断）
        """
        offset = start_offset
        while True:
            if options.page > 0 and options.page_interval > 0:
                # 基准间隔 + 随机抖动：避免固定请求节奏触发风控
                time.sleep(
                    options.page_interval
                    + random.uniform(0, options.page_interval * _FEED_PAGE_JITTER_RATIO)
                )
            data = self._fetch_feed_page(
                uid, offset,
                gate=options.gate, risk_retries=options.risk_retries, page=options.page + 1,
                captcha_handler=options.captcha_handler, captcha_wait=options.captcha_wait,
            )
            options.page += 1
            page_items = data.get("items") if isinstance(data, dict) else None
            if not isinstance(page_items, list) or not page_items:
                return "exhausted"
            added = 0
            hit = False
            oldest_ts: Optional[int] = None
            for item in page_items:
                if not isinstance(item, dict):
                    continue
                author = ((item.get("modules") or {}).get("module_author")) or {}
                pub_ts = _to_int(author.get("pub_ts"))
                pinned = bool((item.get("modules") or {}).get("module_tag")) or bool(author.get("is_top"))
                # 提前停止使用"本页最旧的非置顶动态"（包含被 since 过滤掉的项）
                if pub_ts and not pinned:
                    oldest_ts = pub_ts if oldest_ts is None else min(oldest_ts, pub_ts)
                item_id = str(item.get("id_str") or "")
                if not item_id:
                    continue
                if item_id in known_ids:
                    if stop_ids and item_id in stop_ids:
                        hit = True  # 已进入快照覆盖区间
                    continue
                known_ids.add(item_id)
                if since_ts is not None and pub_ts and pub_ts < since_ts:
                    continue  # 早于 since（含置顶的旧动态）不纳入
                collected.append(item)
                added += 1
                if max_count >= 0 and len(collected) >= max_count:
                    break
            cumulative = base_count + len(collected)
            if options.progress_cb is not None:
                options.progress_cb(options.page, cumulative)
            elif options.display:
                print(
                    f"\r[爬取列表] 第 {options.page} 页，累计 {cumulative} 条{self._crawl_tail(collected)}",
                    end="", flush=True,
                )
                options.printed = True
            if hit:
                return "hit"
            if max_count >= 0 and len(collected) >= max_count:
                return "stopped"
            # 列表时间倒序：本页最旧的非置顶动态已早于 since，说明后续页更旧，可提前停止
            if since_ts is not None and oldest_ts is not None and oldest_ts < since_ts:
                return "stopped"
            next_offset = str(data.get("offset") or "")
            has_more = bool(data.get("has_more", bool(next_offset)))
            if not next_offset or next_offset == offset or not has_more or added == 0:
                return "exhausted"
            offset = next_offset

    @staticmethod
    def _merge_items(*segments) -> list:
        """按段顺序合并（新→旧）并按动态 ID 去重。"""
        merged: list = []
        seen: set = set()
        for segment in segments:
            for item in segment or ():
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id_str") or "")
                if not item_id or item_id in seen:
                    continue
                seen.add(item_id)
                merged.append(item)
        return merged

    # ---- 列表快照 ----

    def load_dynamic_list(self, mid: int | str, *, save_dir=None) -> list[dict]:
        """读取已保存的列表快照（``{save_dir}/{mid}/dynamic_list.json``）。

        不存在或损坏时返回空列表；数据为 :meth:`list_user_dynamics` 的原始 item 列表。
        """
        uid = self.normalize_mid(mid)
        items, _ = self._load_list_snapshot(uid, save_dir=save_dir)
        return items

    def _snapshot_path(self, uid: int, save_dir) -> Path:
        root = Path(save_dir) if save_dir is not None else self.default_dir
        return root / str(uid) / _LIST_SNAPSHOT_NAME

    def _load_list_snapshot(self, uid: int, *, save_dir) -> tuple[list, dict]:
        path = self._snapshot_path(uid, save_dir)
        if not path.is_file():
            return [], {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            logger.warning("[DynamicService] 列表快照读取失败，忽略：%s", exc)
            return [], {}
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return [], {}
        meta = {
            "fetched_at": data.get("fetched_at"),
            "complete": bool(data.get("complete")),
            "count": len(items),
        }
        return [item for item in items if isinstance(item, dict)], meta

    def _save_dynamic_list(self, uid: int, items: list, *, save_dir, complete: bool, display: bool):
        path = self._snapshot_path(uid, save_dir)
        payload = {
            "schema_version": 1,
            "mid": uid,
            "fetched_at": _now_iso(),
            "complete": bool(complete),
            "count": len(items),
            "items": items,
        }
        try:
            # 快照可能很大（数千条 item），用紧凑 JSON 写入
            _write_text(path, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        except OSError as exc:
            logger.warning("[DynamicService] 列表快照保存失败：%s", exc)
            return None
        if display:
            state = "完整" if complete else "未完成"
            print(f"[列表缓存] 已保存 {len(items)} 条（{state}）→ {path}")
        return path

    @staticmethod
    def _crawl_tail(items: list[dict]) -> str:
        """爬取进度尾部：最后爬取条目的发布日期与动态 ID（用于显示已爬到哪一天）。"""
        if not items:
            return ""
        last = items[-1]
        author = ((last.get("modules") or {}).get("module_author")) or {}
        pub_ts = _to_int(author.get("pub_ts"))
        if pub_ts > 0:
            date_text = datetime.fromtimestamp(pub_ts, tz=_BEIJING).strftime("%Y-%m-%d")
        else:
            date_text = str(author.get("pub_time") or "未知")
        return f"，当前最新一条爬取的动态日期：{date_text}，动态id：{last.get('id_str')}"

    def _fetch_feed_page(
        self,
        mid: int,
        offset: str,
        *,
        gate: RiskGate,
        risk_retries: int,
        page: int,
        captcha_handler=None,
        captcha_wait: bool = True,
    ) -> dict:
        """请求一页空间动态；风控退避重试；-352 可暂停等待用户完成验证码。"""
        params = {
            "host_mid": mid,
            "timezone_offset": -480,
            "features": DynamicUrls.DETAIL_FEATURES,
        }
        if offset:
            params["offset"] = offset
        attempt = 0
        while True:
            get_wbi(params)  # 每次尝试都重新签名，避免等待期间 wts 过期
            gate.pause_before_fetch()
            try:
                return self.session.get(DynamicUrls.SPACE_FEED, params=params)
            except BiliAPIError as exc:
                # -352：需要浏览器完成人机验证。暂停等待用户处理后重试本页（不消耗风控重试次数）
                if getattr(exc, "code", 0) == -352 and (captcha_handler is not None or captcha_wait):
                    if self._confirm_captcha(captcha_handler, captcha_wait, page):
                        time.sleep(1.0)
                        continue
                raise
            except (BiliRiskError, BiliForbiddenError) as exc:
                gate.mark_risk()
                if attempt >= risk_retries:
                    raise BiliRiskError(
                        f"列表第 {page} 页请求失败：超过风控重试次数（{risk_retries}）"
                    ) from exc
                wait = _RISK_BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 3.0)
                attempt += 1
                logger.warning(
                    "[DynamicService] 列表第 %d 页触发风控，%.0f 秒后重试（%d/%d）：%s",
                    page, wait, attempt, risk_retries, exc,
                )
                time.sleep(wait)

    @staticmethod
    def _confirm_captcha(captcha_handler, captcha_wait: bool, page: int) -> bool:
        """-352 暂停交互：交给自定义 handler，或控制台提示用户在浏览器完成验证码。

        :return: True 表示"验证已完成，继续爬取"；False 表示放弃（抛出原异常）。
        """
        message = (
            f"抓取列表第 {page} 页时触发 B 站风控验证（-352）。"
            "请在浏览器打开 https://www.bilibili.com 完成验证码/人机验证，验证通过后回到这里继续。"
        )
        if captcha_handler is not None:
            try:
                return bool(captcha_handler(message))
            except Exception:
                logger.warning("[DynamicService] captcha_handler 执行失败，按放弃处理", exc_info=True)
                return False
        if not captcha_wait:
            return False
        print(f"\n[DynamicService] {message}")
        try:
            answer = input("验证完成后输入 y 继续（输入其他内容则终止）：").strip().lower()
        except (EOFError, OSError):
            logger.warning("[DynamicService] 当前环境无法交互输入，按放弃处理")
            return False
        return answer in ("y", "yes", "是")

    def download_user_dynamics(
        self,
        mid: int | str,
        *,
        save_dir=None,
        max_count: int = -1,
        since=None,
        force: bool = False,
        with_comments: bool = True,
        comment_max_count: int = 20,
        comment_sort: str = "hot",
        max_forward_depth: int = 3,
        page_interval: float = _FEED_PAGE_INTERVAL,
        list_progress_cb=None,
        refresh_list: bool = False,
        save_snapshot: bool = True,
        captcha_handler=None,
        captcha_wait: bool = True,
        threads: int = 1,
        account_sessions: Optional[list] = None,
        progress=None,
        progress_cb=None,
    ) -> list[DynamicDownloadResult]:
        """下载某个 UP 主的全部动态（逐条目录化落盘）。

        列表来自 `feed/space`（需 WBI，固定使用主会话以保证可见性一致）；
        多条按发布时间**升序**处理，因此同一天的目录序号即为发布顺序；
        已有成功标记的动态自动跳过。爬取阶段默认页间隔 1 秒（叠加随机抖动）
        并带风控退避重试，大 UP 的列表爬取会先打印逐页进度，随后按动态条数
        展示下载进度。

        `account_sessions` 非空时批量任务**按下标轮询各账号**（全文/评论等
        API 请求分摊到多个账号，降低单账号风控风险）；`threads > 1` 时并发
        下载（目录先按升序预分配，编号顺序不受并发影响）。

        [使用方法]
            service = DynamicService()
            service.download_user_dynamics(36081646)                 # 全部
            service.download_user_dynamics(36081646, max_count=20)   # 最新 20 条
            service.download_user_dynamics(36081646, since="2026-09-01")
            service.download_user_dynamics(36081646, account_sessions=[s1, s2])
            service.download_user_dynamics(36081646, threads=2, account_sessions=[s1, s2])

        :param mid: UP 主 mid（int 或纯数字字符串，必要参数）
        :param save_dir: 输出根目录，默认 ``output/dynamic``
        :param max_count: 最多下载多少条（-1 表示全部）
        :param since: 只下载该日期（含当天，北京时间）之后发布的动态
        :param force: True 时全部重下（复用账本原文件名覆盖）
        :param with_comments: 是否抓评论存档（默认前 20 条热评；大批量建议关闭以降低请求量）
        :param comment_max_count: 评论条数上限；-1 表示全部
        :param comment_sort: ``hot``（最热）或 ``latest``（最新）
        :param max_forward_depth: 转发递归最大深度
        :param page_interval: 列表翻页间隔基准秒数（默认 1.0，附加随机抖动）
        :param list_progress_cb: 列表爬取回调 ``(page, items_found)``；提供时不再打印逐页进度
        :param refresh_list: True 时忽略已保存的列表快照、完整重新爬取（默认 False：
                             读取快照做增量刷新——补最新动态 + 补未爬过的更早动态）
        :param save_snapshot: 全量爬取后是否保存列表快照（默认 True）
        :param captcha_handler: -352 风控验证时的替代交互回调 ``(message) -> bool``
        :param captcha_wait: 触发 -352 时是否在控制台暂停等待用户完成验证码（默认 True）
        :param threads: 并发下载线程数（>1 时启用；需线程安全的进度对象，未提供时自动使用并发版）
        :param account_sessions: 可选：多个账号的 BiliSession 列表，批量任务按下标轮询分摊
        :param progress: 批量进度对象（BatchProgress / ParallelBatchProgress，n=动态条数）
        :param progress_cb: 每条动态完成后的回调 ``(done, total)``
        :return: 每条动态的 DynamicDownloadResult（含缓存命中项），按处理顺序排列
        """
        if max_count < -1:
            raise ValueError("max_count 只能为 -1 或非负整数")
        if threads < 1:
            raise ValueError("threads 必须为正整数")
        uid = self.normalize_mid(mid)
        root = Path(save_dir) if save_dir is not None else self.default_dir
        items = self.list_user_dynamics(
            uid,
            max_count=max_count,
            since=since,
            page_interval=page_interval,
            progress_cb=list_progress_cb,
            use_cache=not refresh_list,
            save_snapshot=save_snapshot,
            save_dir=root,
            captcha_handler=captcha_handler,
            captcha_wait=captcha_wait,
        )
        infos: list[DynamicInfo] = []
        for item in items:
            if not isinstance(item.get("modules"), dict):
                logger.warning("[DynamicService] 跳过不可见的动态：%s", item.get("id_str"))
                continue
            try:
                info = self.parse_item(item)
            except ValueError as exc:
                logger.warning("[DynamicService] 动态解析失败，跳过：%s", exc)
                continue
            infos.append(info)
        if not infos:
            return []
        # 按发布时间升序处理：同一天内的目录序号 = 发布顺序（见开发计划 2.2）
        infos.sort(key=lambda value: (value.author.pub_ts, value.id))

        total = len(infos)
        workers = self._account_worker_services(account_sessions, threads, root)
        # 并发时先按升序预分配目录：编号仍与发布序一致，线程只消费已定路径
        target_dirs: list[Optional[Path]] = [None] * total
        if threads > 1:
            for index, info in enumerate(infos):
                target_dirs[index] = self._resolve_dynamic_dir(info, root)

        if progress is None:
            progress = (
                ParallelBatchProgress(n=total, label="UP主动态")
                if threads > 1
                else BatchProgress(n=total, label="UP主动态", display=True)
            )
        batch = progress

        def run_one(index: int) -> DynamicDownloadResult:
            info = infos[index]
            worker = workers[index % len(workers)]  # 账号按下标轮询
            if info.content.truncated:
                try:
                    info = worker.apply_full_content(info)
                except Exception as exc:  # 全文失败保留摘要
                    logger.warning("[DynamicService] 动态 %s 取全文失败：%s", info.id, exc)
            batch.start(index + 1, dynamic_title(info))
            result = worker._download_resolved(
                info,
                root,
                force=force,
                with_comments=with_comments,
                comment_max_count=comment_max_count,
                comment_sort=comment_sort,
                max_forward_depth=max_forward_depth,
                depth=0,
                ancestors=(),
                progress=None,
                progress_cb=None,
                quiet_media=True,
                target_dir=target_dirs[index],
            )
            total_bytes = sum((entry.size or 0) for entry in result.media)
            batch.update(total_bytes, total_bytes or None)
            batch.finish()
            if result.failures:
                logger.warning("[DynamicService] 动态 %s 存在 %d 个媒体失败", info.id, len(result.failures))
            return result

        try:
            if threads > 1:
                results_by_index: dict = {}
                with ThreadPoolExecutor(max_workers=threads) as executor:
                    future_index = {executor.submit(run_one, index): index for index in range(total)}
                    for future in as_completed(future_index):
                        index = future_index[future]
                        results_by_index[index] = future.result()
                        if progress_cb is not None:
                            progress_cb(len(results_by_index), total)
                return [results_by_index[index] for index in range(total)]
            results: list[DynamicDownloadResult] = []
            for index in range(total):
                results.append(run_one(index))
                if progress_cb is not None:
                    progress_cb(index + 1, total)
            return results
        finally:
            self._close_owned_services(workers)

    @staticmethod
    def _resolve_dynamic_dir(info: DynamicInfo, root: Path) -> Path:
        """定位或分配动态目录（批量预分配用；顺序调用可保证编号=发布序）。"""
        up_dir = Path(root) / str(info.author.mid)
        date_str = DynamicService.dynamic_date(info)
        existing = DynamicService._find_dynamic_dir(up_dir, date_str, info.id)
        return existing if existing is not None else DynamicService._allocate_dynamic_dir(up_dir, date_str)

    def _account_worker_services(self, account_sessions, threads: int, root: Path) -> list:
        """构建账号分流的 worker 服务：任务按下标轮询账号（对齐 VideoService 约定）。

        - ``account_sessions`` 非空：每个账号一个 worker（调用方持有会话，用完不关闭）；
        - 否则 ``threads > 1`` 且主会话是真实 BiliSession：按当前 cookie 创建
          ``threads`` 个隔离会话（由本服务负责关闭）；
        - 其余场景退化为单 worker（顺序执行）。
        """
        if account_sessions:
            return [DynamicService(session=session, default_dir=root) for session in account_sessions]
        if threads <= 1 or not isinstance(self.session, BiliSession):
            return [self]
        services = []
        for _ in range(threads):
            session = BiliSession(
                cookie_path=self.session.cookie_path,
                referer=self.session.referer,
                max_retry=self.session.max_retry,
                timeout=self.session.timeout,
            )
            service = DynamicService(session=session, default_dir=root)
            service._owns_session = True
            services.append(service)
        return services

    @staticmethod
    def _close_owned_services(services) -> None:
        """关闭本服务创建的隔离会话（不关闭调用方传入的会话）。"""
        for service in services or ():
            if not getattr(service, "_owns_session", False):
                continue
            try:
                service.session.close()
            except Exception:
                logger.warning("[DynamicService] 关闭批量下载会话失败", exc_info=True)

    def _download_resolved(
        self,
        info: DynamicInfo,
        root: Path,
        *,
        force: bool,
        with_comments: bool,
        comment_max_count: int,
        comment_sort: str,
        max_forward_depth: int,
        depth: int,
        ancestors: tuple,
        progress,
        progress_cb,
        quiet_media: bool = False,
        target_dir: Optional[Path] = None,
    ) -> DynamicDownloadResult:
        date_str = self.dynamic_date(info)
        up_dir = Path(root) / str(info.author.mid)
        if target_dir is not None:
            dynamic_dir = Path(target_dir)
        else:
            existing = self._find_dynamic_dir(up_dir, date_str, info.id)
            dynamic_dir = existing if existing is not None else self._allocate_dynamic_dir(up_dir, date_str)
        if not force:
            marker = dynamic_dir / _SUCCESS_MARKER
            completed = False
            if marker.is_file():
                try:
                    completed = marker.read_text(encoding="utf-8").strip() == str(info.id)
                except OSError:
                    completed = False
            if completed:  # 完成标记存在才视为缓存命中（未完成/失败目录走重跑补齐）
                return DynamicDownloadResult(
                    path=dynamic_dir,
                    cached=True,
                    md_path=_existing_file(dynamic_dir / "dynamic.md"),
                    comments_path=_existing_file(dynamic_dir / "comments.json"),
                )
        result = DynamicDownloadResult(path=dynamic_dir)

        # 1) 媒体：图片/封面（账本取号）+ 表情/头像/挂件/装扮（manifest 缓存）
        media, failures = self._download_media(
            info, dynamic_dir, up_dir,
            force=force, progress=progress, progress_cb=progress_cb, quiet=quiet_media,
        )
        result.media = media
        result.failures.extend(failures)

        # 2) 转发递归：原动态写入原作者自己的 UP 目录
        forward = info.forward
        if forward is not None and forward.orig is not None:
            if depth >= max_forward_depth:
                result.warnings.append(
                    f"超过转发递归深度 {max_forward_depth}，原动态未下载（ID：{forward.orig_id}）"
                )
            elif forward.orig.id in ancestors or forward.orig.id == info.id:
                result.warnings.append(f"检测到转发循环，原动态未下载（ID：{forward.orig_id}）")
            else:
                sub = self._download_resolved(
                    forward.orig,
                    root,
                    force=force,
                    with_comments=with_comments,
                    comment_max_count=comment_max_count,
                    comment_sort=comment_sort,
                    max_forward_depth=max_forward_depth,
                    depth=depth + 1,
                    ancestors=ancestors + (info.id,),
                    progress=progress,
                    progress_cb=progress_cb,
                    quiet_media=quiet_media,
                )
                forward.archive_dir = _relative_path(dynamic_dir, sub.path)
                result.forwarded.append(sub)

        # 3) 作者资料快照 + 评论存档
        self._update_profile(up_dir, info)
        if with_comments and info.comment_oid > 0 and info.comment_type > 0:
            try:
                comments = self.reply_service.get_comments_by_oid(
                    info.comment_oid,
                    info.comment_type,
                    sort=comment_sort,
                    max_count=comment_max_count,
                )
                comments_path = dynamic_dir / "comments.json"
                _write_json(comments_path, {
                    "dynamic_id": info.id,
                    "oid": info.comment_oid,
                    "comment_type": info.comment_type,
                    "sort": comment_sort,
                    "count": len(comments),
                    "fetched_at": _now_iso(),
                    "items": comments,
                })
                result.comments_path = comments_path
            except Exception as exc:  # 评论失败不阻断整体下载
                logger.warning("[DynamicService] 评论获取失败：%s", exc)
                result.warnings.append(f"评论获取失败：{exc}")

        # 4) 渲染与写盘（txt 最后写 = 完成标记；有失败则留待重跑补齐）
        md_path = dynamic_dir / "dynamic.md"
        _write_text(md_path, render_markdown(info, fetched_at=_now()))
        result.md_path = md_path
        _write_json(dynamic_dir / "raw.json", info.raw)
        payload = info_to_dict(info)
        payload["download"] = {
            "fetched_at": _now_iso(),
            "force": bool(force),
            "failures": list(failures),
        }
        _write_json(dynamic_dir / "dynamic.json", payload)
        if failures:
            result.warnings.append(
                f"存在 {len(failures)} 个媒体下载失败（已自动重试一次），"
                f"已写入 {_FAILED_MARKER}，可重新运行补齐"
            )
            (dynamic_dir / _SUCCESS_MARKER).unlink(missing_ok=True)
            _write_text(dynamic_dir / _FAILED_MARKER, f"{info.id}\n")
        else:
            (dynamic_dir / _FAILED_MARKER).unlink(missing_ok=True)
            _write_text(dynamic_dir / _SUCCESS_MARKER, f"{info.id}\n")
        return result

    # ---- 下载：媒体 ----

    def _download_media(self, info, dynamic_dir, up_dir, *, force, progress, progress_cb, quiet: bool = False):
        """构建并执行媒体任务；返回 (list[DownloadResult], failures)。"""
        date_str = self.dynamic_date(info)
        assets_dir = up_dir / "_assets"
        tasks: list[_MediaTask] = []

        image_allocator = get_asset_allocator(assets_dir / "images")
        for image in info.images:
            if not image.url:
                continue
            key = f"{info.id}/image/{image.index}"
            path = image_allocator.allocate(key, date_str, _ext_from_url(image.url), image.url)
            image.file = _relative_path(dynamic_dir, path)
            tasks.append(_MediaTask(
                kind="image", key=key, url=image.url, path=path,
                allocator=image_allocator, label=f"图片 {image.index:02d}",
            ))
            if image.live_url:
                live_key = f"{info.id}/image/{image.index}/live"
                live_path = image_allocator.allocate(
                    live_key, date_str, _ext_from_url(image.live_url, "mp4"), image.live_url,
                )
                image.live_file = _relative_path(dynamic_dir, live_path)
                tasks.append(_MediaTask(
                    kind="image", key=live_key, url=image.live_url, path=live_path,
                    allocator=image_allocator, label=f"动态图 {image.index:02d}",
                ))

        cover_allocator = get_asset_allocator(assets_dir / "covers")
        for card_index, card in enumerate(info.cards, 1):
            pairs: list[tuple[str, Optional[dict]]] = []
            if card.kind == "goods":
                for item_index, item in enumerate(card.extra.get("items") or [], 1):
                    if isinstance(item, dict) and item.get("cover"):
                        pairs.append((f"item{item_index}", item))
            elif card.cover_url:
                pairs.append(("main", None))
            for sub_key, item in pairs:
                url = str(item.get("cover")) if item is not None else card.cover_url
                key = f"{info.id}/cover/{card_index}/{sub_key}"
                path = cover_allocator.allocate(key, date_str, _ext_from_url(url), url)
                rel = _relative_path(dynamic_dir, path)
                if item is None:
                    card.cover_file = rel
                else:
                    item["cover_file"] = rel
                tasks.append(_MediaTask(
                    kind="cover", key=key, url=url, path=path,
                    allocator=cover_allocator, label=f"封面 {card_index}-{sub_key}",
                ))

        manifest = _get_asset_manifest(assets_dir / "manifest.json")
        emoji_entries = manifest.emoji_entries()
        for emoji in info.emojis:
            if not emoji.url or not emoji.package_id:
                continue
            ext = _ext_from_url(emoji.url)
            name = sanitize_filename(emoji.short_name) or "emoji"
            key = f"{emoji.package_id}/{emoji.emoji_id or name}"
            entry = emoji_entries.get(key)
            if entry and entry.get("file"):
                filename = str(entry["file"])
            else:
                filename = f"{name}.{ext}"
                taken = {
                    str(other.get("file") or "").lower()
                    for other_key, other in emoji_entries.items()
                    if other_key != key and other_key.split("/", 1)[0] == emoji.package_id
                }
                if filename.lower() in taken:
                    filename = f"{name}_{emoji.emoji_id or 'x'}.{ext}"
            target = assets_dir / "emojis" / emoji.package_id / filename
            emoji.file = _relative_path(dynamic_dir, target)
            tasks.append(_MediaTask(
                kind="emoji", key=key, url=emoji.url, path=target, label=f"表情 {emoji.short_name}",
                manifest=manifest, manifest_section="emojis", manifest_text=emoji.text,
            ))

        for kind, name, url, label in (
            ("avatar", info.author.name, info.author.face, "头像"),
            ("pendant", info.author.pendant_name or "pendant",
             info.author.pendant_image_enhance or info.author.pendant_image, "挂件"),
            ("decorate", info.author.decorate_name or "decorate", info.author.decorate_card, "装扮卡"),
        ):
            if not url:
                continue
            ext = _ext_from_url(url)
            safe_name = sanitize_filename(name) or kind
            entry = manifest.asset(kind)
            if entry and entry.get("url") == url and entry.get("file"):
                filename = str(entry["file"])
            else:
                filename = f"{kind}_{safe_name}.{ext}"
            target = assets_dir / filename
            tasks.append(_MediaTask(
                kind=kind, key=kind, url=url, path=target, label=label,
                manifest=manifest, manifest_section="assets", manifest_name=name,
            ))

        if not tasks:
            manifest.save()
            return [], []

        headers = dict(self.session.session.headers)
        batch = progress if progress is not None else BatchProgress(
            n=len(tasks), label="动态媒体", display=not quiet,
        )
        results: list[DownloadResult] = []
        total = len(tasks)
        pending = list(tasks)
        failed_pairs: list[tuple[_MediaTask, Exception]] = []
        # 失败自动重试一次（单文件失败不阻断其余媒体；download_stream 自身也有重试）
        for attempt in range(2):
            failed_pairs = []
            for index, task in enumerate(pending, 1):
                label = task.label if attempt == 0 else f"重试 {task.label}"
                batch.start(index, label)
                try:
                    if not force and task.path.is_file() and task.path.stat().st_size > 0:
                        size = task.path.stat().st_size
                        cached = True
                    else:
                        size = self._download_with_mirrors(
                            task.url, task.path,
                            headers=headers, progress_cb=batch.make_stream_callback(), force=force,
                        )
                        cached = False
                    if task.allocator is not None:
                        task.allocator.mark_done(task.key)
                    if task.manifest is not None:
                        task.manifest.record(task)
                    results.append(DownloadResult(task.path, media_type=task.kind, size=size, cached=cached))
                except Exception as exc:  # 收集失败，下一轮重试或最终记录
                    logger.warning("[DynamicService] 媒体下载失败：%s %s", task.label, exc)
                    failed_pairs.append((task, exc))
                batch.finish()
                if progress_cb is not None:
                    progress_cb(index, total)
            if not failed_pairs:
                break
            if attempt == 0:
                logger.info("[DynamicService] %d 个媒体下载失败，自动重试一次", len(failed_pairs))
                pending = [task for task, _ in failed_pairs]
        manifest.save()
        failures = [f"{task.label}（{task.url}）：{exc}" for task, exc in failed_pairs]
        return results, failures

    # ---- 下载：目录与辅助 ----

    @staticmethod
    def _download_with_mirrors(url: str, path: Path, *, headers, progress_cb, force: bool) -> int:
        """下载单个媒体文件；hdslb CDN 失败时按原 host → i2 → i1 回退重试。

        ``download_stream`` 自带重试与断点续传：切换镜像后若服务器不支持
        Range，会自动丢弃半截文件从头下载，保证内容完整。
        """
        candidates = _mirror_urls(url)
        last_error: Optional[Exception] = None
        for index, candidate in enumerate(candidates):
            try:
                return download_stream(
                    candidate, path, headers=headers,
                    progress_cb=progress_cb,
                    overwrite=force,
                )
            except Exception as exc:
                last_error = exc
                if index < len(candidates) - 1:
                    logger.warning(
                        "[DynamicService] 媒体下载失败，切换镜像重试：%s -> %s（%s）",
                        candidate, candidates[index + 1], exc,
                    )
        raise last_error  # type: ignore[misc]

    @staticmethod
    def dynamic_date(info: DynamicInfo) -> str:
        """动态发布日期（北京时间，``YYYY-MM-DD``）。"""
        if info.author.pub_ts > 0:
            moment = datetime.fromtimestamp(info.author.pub_ts, tz=_BEIJING)
        else:
            moment = datetime.now(_BEIJING)
        return moment.strftime("%Y-%m-%d")

    @staticmethod
    def _marker_dynamic_id(directory: Path) -> str:
        """读取目录归属的动态 ID：成功/失败标记优先，其次 dynamic.json（未完成目录）。"""
        for name in (_SUCCESS_MARKER, _FAILED_MARKER):
            marker = directory / name
            if marker.is_file():
                try:
                    value = marker.read_text(encoding="utf-8").strip()
                    if value:
                        return value
                except OSError:
                    pass
        payload = directory / "dynamic.json"
        if payload.is_file():
            try:
                value = json.loads(payload.read_text(encoding="utf-8")).get("id")
                if value:
                    return str(value).strip()
            except (OSError, ValueError):
                pass
        return ""

    @classmethod
    def _find_dynamic_dir(cls, up_dir: Path, date_str: str, dynamic_id: int) -> Optional[Path]:
        """在 ``{up_dir}/{YYYY-MM}/`` 下查找属于该动态的目录（含未完成目录）。"""
        month_dir = up_dir / date_str[:7]
        if not month_dir.is_dir():
            return None
        for child in sorted(month_dir.iterdir()):
            if not child.is_dir() or not child.name.startswith(date_str + "_"):
                continue
            if cls._marker_dynamic_id(child) == str(dynamic_id):
                return child
        return None

    @staticmethod
    def _allocate_dynamic_dir(up_dir: Path, date_str: str) -> Path:
        """按"追加编号"分配当天动态目录：max(已有序号) + 1，独占创建防并发撞号。"""
        month_dir = up_dir / date_str[:7]
        month_dir.mkdir(parents=True, exist_ok=True)
        used = set()
        for child in month_dir.iterdir():
            if not child.is_dir() or not child.name.startswith(date_str + "_"):
                continue
            suffix = child.name[len(date_str) + 1:]
            if suffix.isdigit():
                used.add(int(suffix))
        sequence = max(used) + 1 if used else 1
        while True:
            candidate = month_dir / f"{date_str}_{sequence}"
            try:
                candidate.mkdir(exist_ok=False)
                return candidate
            except FileExistsError:
                sequence += 1

    @staticmethod
    def _update_profile(up_dir: Path, info: DynamicInfo) -> None:
        """刷新 UP 快照 ``_assets/profile.json``（昵称/头像等可能变化）。"""
        path = up_dir / "_assets" / "profile.json"
        payload = {
            "mid": info.author.mid,
            "name": info.author.name,
            "avatar_url": info.author.face,
            "pendant_name": info.author.pendant_name,
            "decorate_name": info.author.decorate_name,
            "updated_at": _now_iso(),
        }
        try:
            _write_json(path, payload)
        except OSError as exc:
            logger.warning("[DynamicService] profile 写入失败：%s", exc)


@dataclass
class _CrawlOptions:
    """列表爬取配置（增量刷新的多个爬取段共享；page/printed 用于进度展示延续）。"""

    gate: RiskGate
    risk_retries: int = 3
    page_interval: float = _FEED_PAGE_INTERVAL
    captcha_handler: Any = None
    captcha_wait: bool = True
    display: bool = True
    progress_cb: Any = None
    page: int = 0
    printed: bool = False


@dataclass
class _MediaTask:
    """单个媒体下载任务（路径已由分配器/ manifest 唯一确定）。"""

    kind: str
    key: str
    url: str
    path: Path
    label: str
    allocator: Optional[AssetIdAllocator] = None
    manifest: Optional["_AssetManifest"] = None
    manifest_section: str = ""
    manifest_text: str = ""
    manifest_name: str = ""


class _AssetManifest:
    """``_assets/manifest.json`` 读写：可复用资源（头像/挂件/装扮/表情）的来源与落盘映射。

    同一 UP 的并发下载必须经 :func:`_get_asset_manifest` 共享同一实例：
    各自实例会各自持有状态，后写者会覆盖先写者的记录（last-wins 丢失归属）。
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.data: dict = {"assets": {}, "emojis": {}}
        if self.path.is_file():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    for section in ("assets", "emojis"):
                        value = loaded.get(section)
                        if isinstance(value, dict):
                            self.data[section] = {
                                str(key): entry
                                for key, entry in value.items()
                                if isinstance(entry, dict)
                            }
            except (ValueError, OSError) as exc:
                logger.warning("[DynamicService] manifest 读取失败，按空重建：%s", exc)

    def asset(self, key: str) -> Optional[dict]:
        with self._lock:
            return self.data["assets"].get(str(key))

    def emoji_entries(self) -> dict:
        with self._lock:
            return dict(self.data["emojis"])

    def record(self, task: "_MediaTask") -> None:
        """下载成功/缓存命中后回写条目（file/url/状态）。"""
        with self._lock:
            if task.manifest_section == "assets":
                self.data["assets"][str(task.key)] = {
                    "file": task.path.name,
                    "url": task.url,
                    "name": task.manifest_name,
                    "updated_at": _now_iso(),
                }
            elif task.manifest_section == "emojis":
                self.data["emojis"][str(task.key)] = {
                    "file": task.path.name,
                    "url": task.url,
                    "text": task.manifest_text,
                    "updated_at": _now_iso(),
                }

    def save(self) -> None:
        with self._lock:
            if not self.data["assets"] and not self.data["emojis"]:
                return
            _write_json(self.path, self.data)


# 进程内共享的 manifest 注册表：同一文件只保留一个实例（并发 worker 共用锁与状态）
_MANIFESTS: dict = {}
_MANIFESTS_LOCK = threading.Lock()


def _get_asset_manifest(path: Path) -> _AssetManifest:
    key = str(Path(path).resolve())
    with _MANIFESTS_LOCK:
        manifest = _MANIFESTS.get(key)
        if manifest is None:
            manifest = _AssetManifest(path)
            _MANIFESTS[key] = manifest
        return manifest


def _ext_from_url(url: str, default: str = "jpg") -> str:
    ext = Path(urlparse(url).path).suffix.lower().lstrip(".")
    if ext in {"png", "jpg", "jpeg", "gif", "webp", "bmp", "mp4", "m4s"}:
        return ext
    return default


def _relative_path(from_dir: Path, target: Path) -> str:
    """相对路径（POSIX 分隔符），用于 md/json 中的本地引用。"""
    try:
        return Path(os.path.relpath(target, start=from_dir)).as_posix()
    except ValueError:
        return target.as_posix()


def _now() -> datetime:
    return datetime.now(_BEIJING)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _existing_file(path: Path) -> Optional[Path]:
    return path if path.is_file() else None


def _write_text(path: Path, text: str) -> None:
    """临时文件 + os.replace 原子写入（Windows 下 replace 冲突时小步重试）。

    临时文件名带线程/进程标识：并发 worker 同时写同一目标（如 profile.json）
    时不会争抢同一个 ``.tmp`` 路径；最终内容为"最后完成者"。
    Windows 上目标文件可能被短暂占用（杀软扫描/句柄延迟），
    os.replace 会偶发 PermissionError，用短重试平滑掉。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temp_path.write_text(text, encoding="utf-8", newline="\n")
    try:
        last_error: Optional[Exception] = None
        for attempt in range(5):
            try:
                os.replace(temp_path, path)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.05 * (attempt + 1))
        raise last_error  # type: ignore[misc]
    finally:
        temp_path.unlink(missing_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
