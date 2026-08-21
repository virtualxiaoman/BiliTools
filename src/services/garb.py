"""B 站收藏集（DLC）与装扮素材的搜索、解析和下载服务。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, Optional
from urllib.parse import urlparse

from src.api.session import BiliSession
from src.config.path import COLLECTION_OUTPUT_DIR
from src.models.download_model import DownloadResult
from src.urls.garb_urls import GarbUrls
from src.util.downloader import ProgressCallback, download_stream
from src.util.filename import sanitize_filename
from src.util.progress import BatchProgress


_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_SPACE_IMAGE_RE = re.compile(r"^image(?P<index>\d+)_(?P<orientation>landscape|portrait)$")


@dataclass(frozen=True)
class GarbResource:
    """一个等待下载的收藏集或装扮素材。"""

    category: str
    filename_stem: str
    url: str
    media_type: str


class GarbService:
    """下载装扮商城中的收藏集卡片和主题装扮资源。

    文件统一保存到 ``output/收藏集``：收藏集的封面、卡片直接保存在
    ``<名称>`` 目录；装扮按资源类别保存在 ``<名称>/<类别>`` 目录。
    """

    COLLECTION_CATEGORY_ORDER = ("cover", "card_img", "video_list")
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

    def search_items(self, keyword: str, *, page: int = 1, page_size: int = 20) -> list[dict]:
        """搜索收藏集或装扮，返回商城接口的原始条目列表。"""
        keyword = self._normalize_keyword(keyword)
        if page < 1 or page_size < 1:
            raise ValueError("page 和 page_size 必须为正整数")
        data = self.session.get(
            GarbUrls.SEARCH,
            params={"key_word": keyword, "pn": page, "ps": page_size},
        )
        items = data.get("list", []) if isinstance(data, dict) else []
        if not isinstance(items, list):
            raise ValueError("装扮搜索接口返回格式异常：list 不是列表")
        return [item for item in items if isinstance(item, dict)]

    def select_search_item(self, keyword: str) -> dict:
        """选择搜索结果。优先同名精确匹配，否则使用商城排序的第一项。"""
        keyword = self._normalize_keyword(keyword)
        items = self.search_items(keyword)
        if not items:
            raise ValueError(f"未找到与“{keyword}”相关的收藏集或装扮")
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
        return item, detail, len(self.list_resources(item, detail, resource_types=resource_types))

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
        resources = self.list_resources(item, detail, resource_types=resource_types)
        if not resources:
            raise ValueError("该收藏集或装扮没有可下载的素材")

        root = Path(directory) if directory is not None else self.default_dir
        title = sanitize_filename(str(item.get("name") or self._detail_title(detail) or "未命名收藏集"))
        item_root = root / title
        if progress is None:
            progress = BatchProgress(n=len(resources), label=title, display=True)
        headers = dict(self.session.session.headers)
        allocated: set[Path] = set()
        results: list[DownloadResult] = []

        for index, resource in enumerate(resources, 1):
            folder = item_root if self._is_collection(item) else item_root / resource.category
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
                progress_cb(index, len(resources))
            results.append(result)
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
        return resources

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
