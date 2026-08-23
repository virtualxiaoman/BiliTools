"""下载任务请求模型。

该模块定义前端、任务管理器和下载线程之间的稳定输入契约，同时保留
旧版字典任务规格的转换入口，避免破坏现有 GUI、脚本和测试调用方。
"""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from src.models.download_model import VideoQuality


class DownloadSource(StrEnum):
    VIDEO = "bv"
    FAVORITE = "fav"
    SEASON = "season"
    UPLOADER = "up"
    EMOTE = "emote"
    GARB = "garb"
    DRESSUP = "dressup"


class MediaType(StrEnum):
    VIDEO = "video_with_audio"
    AUDIO = "audio"
    GARB = "garb"
    DRESSUP = "dressup"


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    """描述一次下载任务的全部输入参数。"""

    source: DownloadSource
    input_value: object
    save_dir: Path
    media_type: MediaType = MediaType.VIDEO
    quality: VideoQuality = VideoQuality.HD4K
    scope: str = "all"
    page: int = 1
    threads: int = 1
    distribute_accounts: bool = False
    cache_dirs: tuple[Path | str, ...] = field(default_factory=tuple)
    force: bool = False
    pending_resolve: bool = False
    description: str = ""
    emote_full_name: bool = False

    @classmethod
    def from_legacy_dict(cls, spec: Mapping[str, Any]) -> "DownloadRequest":
        """将现有字典规格转换为类型化请求。"""
        if isinstance(spec, cls):
            return spec
        try:
            source = DownloadSource(str(spec["source"]))
            input_value = spec["input"]
            save_dir = Path(spec["save_dir"])
        except KeyError as error:
            raise ValueError(f"下载任务缺少必要字段：{error.args[0]}") from error

        return cls(
            source=source,
            input_value=input_value,
            save_dir=save_dir,
            media_type=MediaType(str(spec.get("media_type", MediaType.VIDEO))),
            quality=VideoQuality(int(spec.get("quality", VideoQuality.HD4K))),
            scope=str(spec.get("scope", "all")),
            page=int(spec.get("page", 1)),
            threads=int(spec.get("threads", 1)),
            distribute_accounts=bool(spec.get("distribute_accounts", False)),
            cache_dirs=tuple(spec.get("cache_dirs") or ()),
            force=bool(spec.get("force", False)),
            pending_resolve=bool(spec.get("pending_resolve", False)),
            description=str(spec.get("desc", "")),
            emote_full_name=bool(spec.get("emote_full_name", False)),
        )

    def with_resolved_input(self, input_value: object, description: str) -> "DownloadRequest":
        """返回短链解析后的新请求，保持请求对象不可变。"""
        return DownloadRequest(
            source=self.source,
            input_value=input_value,
            save_dir=self.save_dir,
            media_type=self.media_type,
            quality=self.quality,
            scope=self.scope,
            page=self.page,
            threads=self.threads,
            distribute_accounts=self.distribute_accounts,
            cache_dirs=self.cache_dirs,
            force=self.force,
            pending_resolve=False,
            description=description,
            emote_full_name=self.emote_full_name,
        )

    def deduplication_key(self) -> tuple:
        """返回与旧管理器一致的任务去重键。"""
        return (
            self.source,
            repr(self.input_value),
            self.scope,
            self.page,
            self.media_type,
            int(self.quality),
            str(self.save_dir),
        )

    def to_legacy_dict(self) -> dict[str, Any]:
        """导出旧字段名，供尚未迁移的外围调用方读取。"""
        return {
            "source": self.source.value,
            "input": self.input_value,
            "scope": self.scope,
            "page": self.page,
            "media_type": self.media_type.value,
            "quality": int(self.quality),
            "save_dir": str(self.save_dir),
            "threads": self.threads,
            "distribute_accounts": self.distribute_accounts,
            "cache_dirs": list(self.cache_dirs),
            "force": self.force,
            "pending_resolve": self.pending_resolve,
            "desc": self.description,
            "emote_full_name": self.emote_full_name,
        }
