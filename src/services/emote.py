"""B 站收藏表情包的获取与下载服务。"""

from pathlib import Path
import re
from typing import Optional
from urllib.parse import urlparse

from src.api.session import BiliSession
from src.config.path import COLLECTION_OUTPUT_DIR
from src.models.download_model import DownloadResult
from src.urls.emote_urls import EmoteUrls
from src.util.downloader import ProgressCallback, download_stream
from src.util.filename import sanitize_filename
from src.util.progress import BatchProgress


class EmoteService:
    """按表情包 package id 获取并下载表情资源。

    动态表情优先保存 ``gif_url``，从而保留动画；静态表情保存 ``url``（通常为 PNG）。
    当首选地址不存在时，会依次回退至 ``webp_url`` 与 ``url``。
    """

    def __init__(self, session: Optional[BiliSession] = None, default_dir=None):
        self.session = session if session is not None else BiliSession()
        self.default_dir = Path(default_dir) if default_dir is not None else COLLECTION_OUTPUT_DIR

    @staticmethod
    def normalize_package_ids(package_ids) -> list[int]:
        """验证并规范化表情包 id，保留输入顺序并去重。"""
        if package_ids is None:
            raise ValueError("需要提供表情包 id")
        if isinstance(package_ids, int):
            values = [str(package_ids)]
        elif isinstance(package_ids, str):
            values = [part.strip() for part in package_ids.split(",")]
        else:
            try:
                values = [str(value).strip() for value in package_ids]
            except TypeError as exc:
                raise ValueError("表情包 id 必须是数字或以英文逗号分隔的数字") from exc

        result = []
        for value in values:
            if not value or not value.isdigit() or int(value) <= 0:
                raise ValueError(f"表情包 id 必须是正整数，收到：{value!r}")
            package_id = int(value)
            if package_id not in result:
                result.append(package_id)
        if not result:
            raise ValueError("需要提供至少一个表情包 id")
        return result

    def get_packages(self, package_ids) -> list[dict]:
        """请求表情包详情，返回 API 的 ``data.packages`` 列表。"""
        ids = self.normalize_package_ids(package_ids)
        data = self.session.get(
            EmoteUrls.PACKAGE,
            params={"business": "reply", "ids": ",".join(map(str, ids))},
        )
        packages = data.get("packages", []) if isinstance(data, dict) else []
        if not isinstance(packages, list):
            raise ValueError("表情包接口返回格式异常：packages 不是列表")
        return packages

    def count_emotes(self, package_ids) -> tuple[list[dict], int]:
        """获取表情包及其中有效表情数量，供 GUI 在下载前初始化进度条。"""
        packages = self.get_packages(package_ids)
        count = sum(
            1
            for package in packages
            if isinstance(package, dict)
            for emote in package.get("emote", [])
            if isinstance(emote, dict) and self._asset_url(emote)
        )
        return packages, count

    def download_packages(
            self,
            package_ids,
            directory=None,
            *,
            progress=None,
            progress_cb: Optional[ProgressCallback] = None,
            packages: Optional[list[dict]] = None,
            use_full_name: bool = False,
    ) -> list[DownloadResult]:
        """下载一个或多个表情包内的全部表情。

        默认文件布局为
        ``output/收藏集/<收藏集名>/<动态表情包|静态表情包|表情包>/别名.扩展名``。
        ``use_full_name=True`` 时，文件名使用 API 的完整 ``text``，否则优先使用
        ``meta.alias``（缺失时回退到 ``text`` 中最后一个下划线后的内容）。
        已存在的同名非空文件不会重复下载，并在结果中标记为缓存命中。
        """
        ids = self.normalize_package_ids(package_ids)
        if packages is None:
            packages = self.get_packages(ids)
        elif not isinstance(packages, list):
            raise ValueError("packages 必须是列表")

        tasks = [
            (package, emote)
            for package in packages
            if isinstance(package, dict)
            for emote in package.get("emote", [])
            if isinstance(emote, dict) and self._asset_url(emote)
        ]
        if not tasks:
            raise ValueError("未获取到可下载的表情，请确认表情包 id 是否正确")

        root = Path(directory) if directory is not None else self.default_dir
        if progress is None:
            progress = BatchProgress(n=len(tasks), label="表情包", display=True)

        positions: dict[int, int] = {}
        results: list[DownloadResult] = []
        headers = dict(self.session.session.headers)
        for index, (package, emote) in enumerate(tasks, 1):
            package_id = self._as_int(package.get("id"), fallback=0)
            positions[package_id] = positions.get(package_id, 0) + 1
            position = positions[package_id]
            collection_name, package_kind = self._package_directory_parts(package, package_id)
            package_dir = root / collection_name / package_kind
            url = self._asset_url(emote)
            extension = self._extension_from_url(url)
            emote_id = self._as_int(emote.get("id"), fallback=position)
            emote_name = self._emote_name(emote, emote_id, use_full_name=use_full_name)
            filename = f"{emote_name}.{extension}"
            save_path = package_dir / filename

            progress.start(index, filename)
            if save_path.exists() and save_path.stat().st_size > 0:
                result = DownloadResult(save_path, media_type="emote", size=save_path.stat().st_size, cached=True)
            else:
                size = download_stream(url, save_path, headers=headers, progress_cb=progress.make_stream_callback())
                result = DownloadResult(save_path, media_type="emote", size=size)
            progress.finish()
            if progress_cb is not None:
                progress_cb(index, len(tasks))
            results.append(result)
        return results

    @staticmethod
    def _as_int(value, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _asset_url(emote: dict) -> str:
        """动态表情优先 GIF，保证下载结果保留动画。"""
        for key in ("gif_url", "webp_url", "url"):
            value = emote.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""

    @staticmethod
    def _extension_from_url(url: str) -> str:
        ext = Path(urlparse(url).path).suffix.lower().lstrip(".")
        return ext if ext in {"png", "jpg", "jpeg", "gif", "webp"} else "png"

    @staticmethod
    def _package_directory_parts(package: dict, package_id: int) -> tuple[str, str]:
        """将包名拆为收藏集名与表情包类型目录。"""
        title = str(package.get("text") or "").strip()
        match = re.match(r"^(?P<collection>.+?)\s+(?P<kind>动态表情包|静态表情包)\s*$", title)
        if match:
            return (
                sanitize_filename(match.group("collection")),
                sanitize_filename(match.group("kind")),
            )
        return sanitize_filename(title or f"表情包 {package_id}"), "表情包"

    @staticmethod
    def _emote_name(emote: dict, emote_id: int, *, use_full_name: bool = False) -> str:
        """返回完整表情名或默认的简称。"""
        text = str(emote.get("text") or "").strip().strip("[]")
        if use_full_name and text:
            return sanitize_filename(text)

        meta = emote.get("meta")
        alias = str(meta.get("alias") or "").strip() if isinstance(meta, dict) else ""
        if not alias:
            alias = text.rsplit("_", 1)[-1] if text else f"表情 {emote_id}"
        return sanitize_filename(alias)
    def search_packages(self, keyword: str, *, page: int = 1, page_size: int = 20) -> list[dict]:
        """按关键词搜索表情包（需登录，返回当前账号可用的表情包）。

        接口 ``x/emote/package/search`` 仅返回账号已拥有/可用的表情包，多数账号下
        为空列表；未登录或解析异常时返回 ``[]``，不抛错。每个返回项结构同
        ``get_packages`` 的 package 结构（含 ``id``/``text``）。
        """
        keyword = str(keyword or "").strip()
        if not keyword:
            return []
        if page < 1 or page_size < 1:
            raise ValueError("page 和 page_size 必须为正整数")
        try:
            data = self.session.get(
                EmoteUrls.SEARCH,
                params={"business": "reply", "key_word": keyword, "pn": page, "ps": page_size},
            )
        except Exception:
            return []
        entries = data.get("list") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            entries = data.get("packages") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            return []
        return [entry for entry in entries if isinstance(entry, dict)]
