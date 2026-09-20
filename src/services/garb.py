"""B 站收藏集（DLC）与装扮素材的搜索、解析和下载服务。"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import re
from typing import Iterable, Optional
from urllib.parse import urlparse

from src.api.session import BiliSession
from src.config.path import COLLECTION_OUTPUT_DIR
from src.models.download_model import DownloadResult
from src.services.emote import EmoteService
from src.urls.garb_urls import GarbUrls
from src.util.downloader import ProgressCallback, download_stream
from src.util.filename import sanitize_filename
from src.util.progress import BatchProgress

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_SPACE_IMAGE_RE = re.compile(r"^image(?P<index>\d+)_(?P<orientation>landscape|portrait)$")
_COLLECTION_REWARD_CATEGORY = "奖励素材"


@dataclass(frozen=True)
class GarbResource:
    """一个等待下载的收藏集或装扮素材。"""

    category: str
    filename_stem: str
    url: str
    media_type: str


class _OffsetProgress:
    """把子服务的文件序号映射到当前收藏集的总进度。"""

    def __init__(self, progress, offset: int):
        self._progress = progress
        self._offset = offset

    def start(self, index: int, name: str) -> None:
        self._progress.start(self._offset + index, name)

    def finish(self) -> None:
        self._progress.finish()

    def make_stream_callback(self):
        return self._progress.make_stream_callback()


class GarbService:
    """下载装扮商城中的收藏集卡片和主题装扮资源。

    文件统一保存到 ``output/收藏集``：收藏集的封面、卡片直接保存在
    ``<名称>`` 目录；装扮按资源类别保存在 ``<名称>/<类别>`` 目录。
    """

    COLLECTION_CATEGORY_ORDER = ("cover", "card_img", "video_list", "collect_reward", "emoji_package")
    COLLECTION_CATEGORIES = set(COLLECTION_CATEGORY_ORDER)
    SUIT_CATEGORY_ORDER = (
        "card", "emoji_package", "card_bg", "thumbup", "loading",
        "play_icon", "skin", "space_bg",
    )
    SUIT_CATEGORIES = set(SUIT_CATEGORY_ORDER)
    _SUIT_DIR_NAMES = {
        "card": "动态卡片",
        "emoji_package": "表情包",
        "card_bg": "评论装扮",
        "thumbup": "点赞特效",
        "loading": "加载动画",
        "play_icon": "进度条",
        "skin": "个性主题",
        "space_bg": "空间海报",
    }

    def __init__(self, session: Optional[BiliSession] = None, default_dir=None):
        self.session = session if session is not None else BiliSession()
        self.default_dir = Path(default_dir) if default_dir is not None else COLLECTION_OUTPUT_DIR
        self._emote_packages_cache: dict[tuple[int, ...], tuple[list[dict], int]] = {}

    def search_items(self, keyword: str, *, page: int = 1, page_size: int = 20) -> list[dict]:
        """搜索收藏集或装扮，返回商城接口的原始条目列表。

        搜索接口在“没有匹配结果”时可能返回 ``{"list": None}`` 或其他空值，
        这表示空结果而不是接口故障，因此统一转换为空列表交给上层处理；只有
        ``list`` 存在且是明显错误的类型时，才抛出格式异常，避免把真实的
        API 变更静默当成“没有搜索结果”。
        """
        keyword = self._normalize_keyword(keyword)
        if page < 1 or page_size < 1:
            raise ValueError("page 和 page_size 必须为正整数")
        data = self.session.get(
            GarbUrls.SEARCH,
            params={"key_word": keyword, "pn": page, "ps": page_size},
        )
        if not isinstance(data, dict):
            raise ValueError("装扮搜索接口返回格式异常：响应不是对象")
        items = data.get("list", [])
        # B 站在无结果时可能返回 null 或其他空值；此时应沿着空结果流程继续，
        # 由界面提示“未找到相关装扮或表情包”，而不是显示红色报错。
        if not items:
            return []
        if not isinstance(items, list):
            raise ValueError("装扮搜索接口返回格式异常：list 不是列表")
        return [item for item in items if isinstance(item, dict)]

    def select_search_item(self, keyword: str) -> dict:
        """选择搜索结果。优先同名精确匹配，否则使用商城排序的第一项。"""
        keyword = self._normalize_keyword(keyword)
        items = self.search_items(keyword)
        if not items:
            raise ValueError(f"未找到与'{keyword}'相关的收藏集或装扮")
        folded = keyword.casefold()
        for item in items:
            if str(item.get("name") or "").strip().casefold() == folded:
                return item
        return items[0]

    def get_collection_detail(self, act_id, lottery_id) -> dict:
        """获取收藏集详情。"""
        if not str(act_id).strip() or not str(lottery_id).strip():
            raise ValueError("收藏集缺少 act_id 或 lottery_id")
        data = self.session.get(
            GarbUrls.COLLECTION_DETAIL,
            params={"act_id": act_id, "lottery_id": lottery_id},
        )
        if not isinstance(data, dict):
            raise ValueError("收藏集详情接口返回格式异常")
        return data

    def get_suit_detail(self, item_id) -> dict:
        """获取主题装扮详情。"""
        item_id = self._positive_id(item_id, "装扮 item_id")
        data = self.session.get(GarbUrls.SUIT_DETAIL, params={"item_id": item_id})
        if not isinstance(data, dict):
            raise ValueError("装扮详情接口返回格式异常")
        return data

    def get_detail(self, item: dict) -> dict:
        """根据搜索项类型获取其详情。``part_id == 0`` 表示收藏集。"""
        if not isinstance(item, dict):
            raise ValueError("搜索项必须是字典")
        if self._is_collection(item):
            properties = item.get("properties")
            properties = properties if isinstance(properties, dict) else {}
            return self.get_collection_detail(
                properties.get("dlc_act_id"), properties.get("dlc_lottery_id"),
            )
        return self.get_suit_detail(item.get("item_id"))

    def prepare_download(
            self, keyword: str, *, resource_types: Optional[Iterable[str]] = None,
    ) -> tuple[dict, dict, int]:
        """搜索并获取详情，返回 ``(item, detail, 资源数量)`` 以供 GUI 初始化进度。"""
        item = self.select_search_item(keyword)
        detail = self.get_detail(item)
        selected = self._normalize_resource_types(item, resource_types)
        resource_count = len(self.list_resources(item, detail, resource_types=selected))
        if self._is_collection(item) and "emoji_package" in selected:
            _, emote_count = self._get_collection_emote_packages(detail)
            resource_count += emote_count
        return item, detail, resource_count

    def list_resources(
            self, item: dict, detail: dict, *, resource_types: Optional[Iterable[str]] = None,
    ) -> list[GarbResource]:
        """从详情中提取全部可下载资源，不发起媒体下载。"""
        selected = self._normalize_resource_types(item, resource_types)
        if self._is_collection(item):
            return self._list_collection_resources(detail, selected)
        return self._list_suit_resources(detail, selected)

    def download_by_keyword(
            self, keyword: str, directory=None, *, resource_types: Optional[Iterable[str]] = None,
            progress=None, progress_cb: Optional[ProgressCallback] = None,
    ) -> list[DownloadResult]:
        """按关键词下载商城排序第一项（若同名则优先同名项）的全部素材。"""
        item, detail, _ = self.prepare_download(keyword, resource_types=resource_types)
        return self.download_item(
            item, directory, resource_types=resource_types, detail=detail,
            progress=progress, progress_cb=progress_cb,
        )

    def download_item(
            self, item: dict, directory=None, *, resource_types: Optional[Iterable[str]] = None,
            detail: Optional[dict] = None, progress=None,
            progress_cb: Optional[ProgressCallback] = None,
    ) -> list[DownloadResult]:
        """下载已选择搜索项的素材；可传 ``detail`` 复用先前请求的详情。"""
        if not isinstance(item, dict):
            raise ValueError("搜索项必须是字典")
        detail = self.get_detail(item) if detail is None else detail
        selected = self._normalize_resource_types(item, resource_types)
        resources = self.list_resources(item, detail, resource_types=selected)
        emote_packages: list[dict] = []
        emote_count = 0
        if self._is_collection(item) and "emoji_package" in selected:
            emote_packages, emote_count = self._get_collection_emote_packages(detail)
        if not resources and not emote_count:
            raise ValueError("该收藏集或装扮没有可下载的素材")

        root = Path(directory) if directory is not None else self.default_dir
        title = sanitize_filename(str(item.get("name") or self._detail_title(detail) or "未命名收藏集"))
        item_root = root / title
        total_count = len(resources) + emote_count
        if progress is None:
            progress = BatchProgress(n=total_count, label=title, display=True)
        headers = dict(self.session.session.headers)
        allocated: set[Path] = set()
        results: list[DownloadResult] = []

        for index, resource in enumerate(resources, 1):
            folder = item_root / resource.category if self._is_collection(item) and resource.category else (
                item_root / resource.category
            )
            path = self._make_unique_path(folder, resource.filename_stem, resource.url, allocated)
            progress.start(index, path.name)
            if path.exists() and path.stat().st_size > 0:
                result = DownloadResult(path, media_type=resource.media_type, size=path.stat().st_size, cached=True)
            else:
                size = download_stream(
                    resource.url, path, headers=headers, progress_cb=progress.make_stream_callback(),
                )
                result = DownloadResult(path, media_type=resource.media_type, size=size)
            progress.finish()
            if progress_cb is not None:
                progress_cb(index, total_count)
            results.append(result)

        if emote_count:
            package_ids = self._collection_emote_package_ids(detail)
            emote_progress = _OffsetProgress(progress, len(resources))
            emote_progress_cb = self._offset_progress_callback(
                progress_cb, offset=len(resources), total=total_count,
            )
            results.extend(
                EmoteService(self.session).download_packages(
                    package_ids,
                    root,
                    progress=emote_progress,
                    progress_cb=emote_progress_cb,
                    packages=emote_packages,
                )
            )
        return results

    @staticmethod
    def _normalize_keyword(keyword: str) -> str:
        value = str(keyword or "").strip()
        if not value:
            raise ValueError("需要提供收藏集或装扮的搜索关键词")
        return value

    @staticmethod
    def _positive_id(value, label: str) -> int:
        value = str(value or "").strip()
        if not value.isdigit() or int(value) <= 0:
            raise ValueError(f"{label}必须是正整数")
        return int(value)

    @staticmethod
    def _is_collection(item: dict) -> bool:
        try:
            return int(item.get("part_id", 0)) == 0
        except (TypeError, ValueError):
            return False

    def _normalize_resource_types(self, item: dict, resource_types: Optional[Iterable[str]]) -> set[str]:
        allowed = self.COLLECTION_CATEGORIES if self._is_collection(item) else self.SUIT_CATEGORIES
        if resource_types is None:
            return set(allowed)
        if isinstance(resource_types, str):
            values = [value.strip() for value in resource_types.split(",")]
        else:
            values = [str(value).strip() for value in resource_types]
        selected = set(values)
        invalid = selected - allowed
        if invalid:
            raise ValueError(f"不支持的资源类型：{', '.join(sorted(invalid))}")
        return selected

    @staticmethod
    def _collection_emote_package_ids(detail: dict) -> list[int]:
        """提取收藏集奖励链中关联的表情包 package id（保序去重）。"""
        collect_list = detail.get("collect_list") if isinstance(detail, dict) else None
        collect_chain = collect_list.get("collect_chain") if isinstance(collect_list, dict) else None
        if not isinstance(collect_chain, list):
            return []

        package_ids: list[int] = []
        seen: set[int] = set()
        for entry in collect_chain:
            if not isinstance(entry, dict):
                continue
            type_name = str(entry.get("redeem_item_type_name") or "").strip()
            package_id = str(entry.get("redeem_item_id") or "").strip()
            if "表情包" not in type_name or not package_id.isdigit():
                continue
            parsed_id = int(package_id)
            if parsed_id > 0 and parsed_id not in seen:
                seen.add(parsed_id)
                package_ids.append(parsed_id)
        return package_ids

    def _get_collection_emote_packages(self, detail: dict) -> tuple[list[dict], int]:
        """获取收藏集表情包详情以及其中实际可下载的表情数。"""
        package_ids = tuple(self._collection_emote_package_ids(detail))
        if not package_ids:
            return [], 0
        if package_ids not in self._emote_packages_cache:
            try:
                self._emote_packages_cache[package_ids] = EmoteService(self.session).count_emotes(package_ids)
            except Exception:
                # 表情包是收藏集的附加资源。接口异常或个别包失效时，仍应下载
                # 同一收藏集的封面/卡片，并且不能让并发批量任务整体失败。
                logger.debug(
                    "收藏集表情包详情不可用，跳过 package ids=%s",
                    package_ids,
                    exc_info=True,
                )
                self._emote_packages_cache[package_ids] = ([], 0)
        return self._emote_packages_cache[package_ids]

    @staticmethod
    def _offset_progress_callback(progress_cb, *, offset: int, total: int):
        if progress_cb is None:
            return None

        def callback(index: int, _count: int) -> None:
            progress_cb(offset + index, total)

        return callback

    def _list_collection_resources(self, detail: dict, selected: set[str]) -> list[GarbResource]:
        if not isinstance(detail, dict):
            return []
        resources: list[GarbResource] = []
        if "cover" in selected:
            self._append_resource(resources, "", "封面", detail.get("cover"), "cover")
        for item in detail.get("item_list", []):
            card = item.get("card_info") if isinstance(item, dict) else None
            if not isinstance(card, dict):
                continue
            name = str(card.get("card_name") or "卡片")
            if "card_img" in selected:
                self._append_resource(resources, "", name, card.get("card_img"), "card")
            if "video_list" in selected:
                videos = card.get("video_list")
                if isinstance(videos, list) and videos:
                    self._append_resource(resources, "", name, videos[0], "card_video")
        if "collect_reward" in selected:
            self._append_collection_reward_resources(resources, detail)
        return resources

    def _append_collection_reward_resources(self, resources: list[GarbResource], detail: dict) -> None:
        """提取收藏集奖励的预览图、详情图以及 ``card_item`` 内的素材。"""
        collect_list = detail.get("collect_list") if isinstance(detail, dict) else None
        if not isinstance(collect_list, dict):
            return

        seen_urls: set[str] = set()
        entry_index = 0
        for field in ("collect_infos", "collect_chain"):
            entries = collect_list.get(field)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                entry_index += 1
                self._append_collection_reward_entry(resources, entry, entry_index, seen_urls)

    def _append_collection_reward_entry(
            self, resources: list[GarbResource], entry: dict, index: int, seen_urls: set[str],
    ) -> None:
        name = str(entry.get("redeem_item_name") or entry.get("redeem_item_type_name") or "奖励")
        identity = str(entry.get("collect_id") or entry.get("redeem_item_id") or index)
        prefix = sanitize_filename(f"{name}_{identity}")

        for key in ("redeem_item_image", "redeem_item_image_download", "redeem_detail_image"):
            self._append_collection_reward_url(resources, prefix, key, entry.get(key), seen_urls)
        self._append_collection_reward_value(
            resources, prefix, "redeem_detail_video", entry.get("redeem_detail_videos"), seen_urls,
        )

        optional_items = entry.get("redeem_item_optional_list")
        if isinstance(optional_items, list):
            for optional_index, optional in enumerate(optional_items, 1):
                if not isinstance(optional, dict):
                    continue
                self._append_collection_reward_url(
                    resources, prefix, f"optional_{optional_index}", optional.get("image"), seen_urls,
                )

        card_item = entry.get("card_item")
        if not isinstance(card_item, dict):
            return

        # ``watermark_animation`` 是带水印预览；同一奖励提供
        # ``animation_video_urls`` 时，后者为无水印版本，必须优先且仅下载后者。
        plain_animations = self._nested_urls_for_key(card_item, "animation_video_urls")
        if plain_animations:
            for animation_index, url in enumerate(plain_animations, 1):
                self._append_collection_reward_url(
                    resources, prefix, f"animation_{animation_index}", url, seen_urls,
                )
        else:
            for animation_index, url in enumerate(
                    self._nested_urls_for_key(card_item, "watermark_animation"), 1,
            ):
                self._append_collection_reward_url(
                    resources, prefix, f"watermark_animation_{animation_index}", url, seen_urls,
                )

        self._append_card_item_resources(resources, prefix, card_item, seen_urls)

    def _append_card_item_resources(
            self, resources: list[GarbResource], prefix: str, value, seen_urls: set[str],
            path: tuple[str, ...] = (),
    ) -> None:
        """递归提取 ``card_item`` 的非动画资源，动画由上层按水印优先级处理。"""
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"animation_video_urls", "watermark_animation", "jump_url"}:
                    continue
                self._append_card_item_resources(resources, prefix, child, seen_urls, path + (str(key),))
            return
        if isinstance(value, list):
            for item_index, child in enumerate(value, 1):
                self._append_card_item_resources(
                    resources, prefix, child, seen_urls, path + (str(item_index),),
                )
            return
        if self._is_url(value):
            label = "_".join(path[-4:]) or "resource"
            self._append_collection_reward_url(resources, prefix, label, value, seen_urls)

    @staticmethod
    def _nested_urls_for_key(value, target_key: str) -> list[str]:
        urls: list[str] = []

        def collect(node) -> None:
            if isinstance(node, dict):
                for key, child in node.items():
                    if key == target_key:
                        collect_urls(child)
                    else:
                        collect(child)
            elif isinstance(node, list):
                for child in node:
                    collect(child)

        def collect_urls(node) -> None:
            if GarbService._is_url(node):
                urls.append(str(node))
            elif isinstance(node, (list, tuple)):
                for child in node:
                    collect_urls(child)
            elif isinstance(node, dict):
                for child in node.values():
                    collect_urls(child)

        collect(value)
        return urls

    def _append_collection_reward_value(
            self, resources: list[GarbResource], prefix: str, label: str, value, seen_urls: set[str],
    ) -> None:
        if self._is_url(value):
            self._append_collection_reward_url(resources, prefix, label, value, seen_urls)
        elif isinstance(value, list):
            for index, item in enumerate(value, 1):
                self._append_collection_reward_value(resources, prefix, f"{label}_{index}", item, seen_urls)

    @staticmethod
    def _append_collection_reward_url(
            resources: list[GarbResource], prefix: str, label: str, url, seen_urls: set[str],
    ) -> None:
        if not GarbService._is_url(url):
            return
        url = str(url)
        if url in seen_urls:
            return
        seen_urls.add(url)
        media_type = "collection_reward_video" if Path(urlparse(url).path).suffix.lower() in {".mp4", ".webm"} else (
            "collection_reward"
        )
        resources.append(
            GarbResource(
                _COLLECTION_REWARD_CATEGORY,
                sanitize_filename(f"{prefix}_{label}"),
                url,
                media_type,
            )
        )

    def _list_suit_resources(self, detail: dict, selected: set[str]) -> list[GarbResource]:
        suit_items = detail.get("suit_items") if isinstance(detail, dict) else None
        if not isinstance(suit_items, dict):
            return []
        resources: list[GarbResource] = []
        for resource_type in self.SUIT_CATEGORY_ORDER:
            if resource_type not in selected:
                continue
            entries = suit_items.get(resource_type, [])
            if not isinstance(entries, list):
                continue
            category = self._SUIT_DIR_NAMES[resource_type]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if resource_type == "emoji_package":
                    self._append_emoji_resources(resources, category, entry)
                else:
                    self._append_suit_entry_resources(resources, category, resource_type, entry)
        return resources

    def _append_emoji_resources(self, resources: list[GarbResource], category: str, entry: dict) -> None:
        nested = entry.get("items")
        if not isinstance(nested, list):
            nested = [entry]
        for item in nested:
            if not isinstance(item, dict):
                continue
            props = item.get("properties")
            props = props if isinstance(props, dict) else {}
            name = self._short_emoji_name(str(item.get("name") or "表情"))
            self._append_resource(resources, category, name, props.get("image"), "emoji")

    def _append_suit_entry_resources(self, resources: list[GarbResource], category: str, resource_type: str,
                                     entry: dict) -> None:
        props = entry.get("properties")
        props = props if isinstance(props, dict) else {}
        name = str(entry.get("name") or category)
        if resource_type == "card":
            self._append_resource(resources, category, name, props.get("image"), "card")
            self._append_resource(resources, category, f"{name}_fans", props.get("fans_image"), "card")
            return
        if resource_type == "loading":
            self._append_resource(resources, category, name, props.get("loading_url"), "loading")
            self._append_resource(resources, category, f"{name}_frame", props.get("loading_frame_url"), "loading")
            return
        for key, value in props.items():
            if not self._is_url(value):
                continue
            stem = self._suit_filename_stem(name, resource_type, key)
            self._append_resource(resources, category, stem, value, resource_type)

    @staticmethod
    def _suit_filename_stem(name: str, resource_type: str, key: str) -> str:
        if resource_type in {"card_bg", "thumbup"} and key == "image":
            return name
        match = _SPACE_IMAGE_RE.match(key) if resource_type == "space_bg" else None
        if match:
            return f"{name}_{match.group('index')}_{match.group('orientation')}"
        return f"{name}_{key}"

    @staticmethod
    def _short_emoji_name(name: str) -> str:
        value = name.strip().strip("[]")
        return value.rsplit("_", 1)[-1] if value else "表情"

    @staticmethod
    def _append_resource(resources: list[GarbResource], category: str, stem: str, url, media_type: str) -> None:
        if GarbService._is_url(url):
            resources.append(GarbResource(category, sanitize_filename(str(stem)), str(url), media_type))

    @staticmethod
    def _is_url(value) -> bool:
        return isinstance(value, str) and bool(_URL_RE.match(value.strip()))

    @staticmethod
    def _detail_title(detail: dict) -> str:
        if not isinstance(detail, dict):
            return ""
        return str(detail.get("name") or detail.get("title") or "")

    @staticmethod
    def _extension_from_url(url: str) -> str:
        suffix = Path(urlparse(url).path).suffix.lower().lstrip(".")
        return suffix if suffix and suffix.isalnum() and len(suffix) <= 10 else "bin"

    def _make_unique_path(self, folder: Path, stem: str, url: str, allocated: set[Path]) -> Path:
        extension = self._extension_from_url(url)
        safe_stem = sanitize_filename(stem)
        candidate = folder / f"{safe_stem}.{extension}"
        suffix = 2
        while candidate in allocated:
            candidate = folder / f"{safe_stem}_{suffix}.{extension}"
            suffix += 1
        allocated.add(candidate)
        return candidate
