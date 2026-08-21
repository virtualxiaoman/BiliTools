"""装扮统一服务：同时搜索表情包、收藏集与主题装扮，并支持批量并发下载。

界面“装扮”页签的搜索结果由三类组成：
- ``emoji``：EmoteService 的表情包 package；
- ``collection``：装扮商城里的收藏集（DLC）；
- ``suit``：装扮商城里的主题装扮。

批量下载时支持 ``threads > 1`` 并发，并在传入多账号 ``BiliSession`` 列表时
按任务下标轮询分摊账号，降低单个账号的风控风险。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from src.api.session import BiliSession
from src.config.path import COLLECTION_OUTPUT_DIR
from src.models.download_model import DownloadResult
from src.services.emote import EmoteService
from src.services.garb import GarbService
from src.util.downloader import ProgressCallback


_PREFIXES = {
    "emoji": "表情包",
    "collection": "收藏集",
    "suit": "装扮",
}


@dataclass(frozen=True)
class DressupItem:
    """一条可下载的装扮搜索结果。``kind`` 为 emoji / collection / suit。"""

    kind: str
    name: str
    payload: dict

    @property
    def display_name(self) -> str:
        prefix = _PREFIXES.get(self.kind, self.kind)
        return f"{prefix}-{self.name}"

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "display_name": self.display_name,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DressupItem":
        if not isinstance(data, dict):
            raise ValueError("装扮下载项必须是字典")
        payload = data.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("装扮下载项缺少 payload")
        return cls(
            str(data.get("kind") or ""),
            str(data.get("name") or ""),
            payload,
        )


class DressupService:
    """装扮页签的搜索与批量下载服务。"""

    def __init__(self, session: Optional[BiliSession] = None, default_dir=None):
        self.session = session if session is not None else BiliSession()
        self.default_dir = Path(default_dir) if default_dir is not None else COLLECTION_OUTPUT_DIR

    # ---- 搜索 ----

    def search(self, keyword: str, *, page: int = 1, page_size: int = 50) -> list[DressupItem]:
        """同时搜索三类内容，按 表情包 → 收藏集 → 主题装扮 的顺序返回。"""
        keyword = str(keyword or "").strip()
        if not keyword:
            raise ValueError("需要提供搜索关键词")
        if page < 1 or page_size < 1:
            raise ValueError("page 和 page_size 必须为正整数")

        garb_items = GarbService(self.session).search_items(
            keyword, page=page, page_size=page_size,
        )
        emote_items = EmoteService(self.session).search_packages(
            keyword, page=page, page_size=page_size,
        )

        collections: list[DressupItem] = []
        suits: list[DressupItem] = []
        for raw in garb_items:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            if not name:
                continue
            kind = "collection" if GarbService._is_collection(raw) else "suit"
            (collections if kind == "collection" else suits).append(
                DressupItem(kind, name, raw)
            )

        emojis: list[DressupItem] = []
        for raw in emote_items:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("text") or raw.get("name") or "").strip()
            if not name:
                continue
            emojis.append(DressupItem("emoji", name, raw))

        return emojis + collections + suits

    # ---- 批量下载 ----

    def download_items(
        self,
        items: Iterable,
        directory=None,
        *,
        threads: int = 1,
        account_sessions: Optional[list[BiliSession]] = None,
        progress=None,
        progress_cb: Optional[ProgressCallback] = None,
        use_full_name: bool = False,
    ) -> list[DownloadResult]:
        """按勾选顺序批量下载；``threads > 1`` 时并发执行并轮询分摊账号。"""
        normalized = [self._normalize_item(item) for item in items]
        if not normalized:
            raise ValueError("请选择要下载的装扮/表情包")

        root = Path(directory) if directory is not None else self.default_dir
        if threads < 1:
            threads = 1
        sessions = list(account_sessions) if account_sessions else []

        if len(normalized) <= 1 or threads <= 1:
            results = [
                self._download_one(
                    item, root, sessions, index,
                    progress=progress, progress_cb=progress_cb,
                    use_full_name=use_full_name,
                )
                for index, item in enumerate(normalized)
            ]
        else:
            results: list = [None] * len(normalized)
            with ThreadPoolExecutor(max_workers=threads) as pool:
                future_to_index = {
                    pool.submit(
                        self._download_one, item, root, sessions, index,
                        progress=progress, progress_cb=progress_cb,
                        use_full_name=use_full_name,
                    ): index
                    for index, item in enumerate(normalized)
                }
                for future in as_completed(future_to_index):
                    results[future_to_index[future]] = future.result()

        flat: list[DownloadResult] = []
        for result in results:
            if result:
                flat.extend(result)
        return flat

    # ---- 内部 ----

    @staticmethod
    def _normalize_item(item) -> DressupItem:
        if isinstance(item, DressupItem):
            return item
        return DressupItem.from_dict(item)

    @staticmethod
    def _package_id(payload: dict) -> int:
        try:
            value = int(payload.get("id"))
        except (TypeError, ValueError) as exc:
            raise ValueError("表情包搜索结果缺少有效的 package id") from exc
        if value <= 0:
            raise ValueError("表情包 package id 必须是正整数")
        return value

    def _download_one(
        self,
        item: DressupItem,
        root: Path,
        sessions: list[BiliSession],
        index: int,
        *,
        progress=None,
        progress_cb: Optional[ProgressCallback] = None,
        use_full_name: bool = False,
    ) -> list[DownloadResult]:
        session = sessions[index % len(sessions)] if sessions else self.session
        if item.kind == "emoji":
            service = EmoteService(session, default_dir=root)
            return service.download_packages(
                [self._package_id(item.payload)],
                root,
                progress=progress,
                progress_cb=progress_cb,
                use_full_name=use_full_name,
            )
        if item.kind in ("collection", "suit"):
            service = GarbService(session, default_dir=root)
            return service.download_item(
                item.payload, root, progress=progress, progress_cb=progress_cb,
            )
        raise ValueError(f"不支持的装扮类型：{item.kind}")
