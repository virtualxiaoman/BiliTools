"""
收藏夹相关的数据模型。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FavInfo:
    """收藏夹信息（x/v3/fav/folder/info 返回的 data 字段）。"""

    id: int = 0  # media_id
    fid: int = 0  # 收藏夹 fid
    mid: int = 0  # 收藏夹所属用户UID
    title: str = ""  # 收藏夹名称
    media_count: int = 0  # 收藏的视频数量

    # 原始响应（便于排查/调试）
    raw: Optional[dict] = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, data: dict) -> "FavInfo":
        return cls(
            id=data.get("id", 0),
            fid=data.get("fid", 0),
            mid=data.get("mid", 0),
            title=data.get("title", ""),
            media_count=data.get("media_count", 0),
            raw=data,
        )
