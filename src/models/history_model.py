"""
历史记录相关的数据模型。

- `HistoryItem`   一条历史记录（archive 类型含视频观看进度）
- `HistoryPage`   一页历史记录 + 游标（用于继续翻页）
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HistoryItem:
    """一条历史记录条目。"""

    oid: int = 0  # 条目 id（稿件avid/剧集ssid/直播间id等）
    business: str = ""  # 业务类型：archive(视频)/pgc(剧集)/live(直播)/article-list(文集)/article(文章)
    bvid: str = ""  # business=archive 时的 BV 号
    progress: int = 0  # 观看进度（秒）
    duration: int = 0  # 视频时长（秒）
    view_at: int = 0  # 观看时间戳
    title: str = ""  # 标题（如需展示）

    # 原始条目（保留供二次处理）
    raw: Optional[dict] = field(default=None, repr=False)

    @property
    def view_percent(self) -> str:
        """观看进度百分比。"""
        if self.progress == -1:
            # B 站用 -1 表示已看完
            return "100.00%"
        if self.progress < 0 or self.duration <= 0:
            # 进度为负（除 -1 外）或时长无效时，无法计算百分比
            return "-1.00%"
        return f"{round(self.progress / self.duration * 100, 2):.2f}%"


@dataclass
class HistoryPage:
    """一页历史记录与下一页游标。"""

    items: list = field(default_factory=list)  # HistoryItem 列表
    has_more: bool = False  # 是否还有下一页
    max: int = 0  # 下一页游标 max
    business: str = ""  # 下一页游标 business
    view_at: int = 0  # 下一页游标 view_at

    @classmethod
    def from_json(cls, data: dict) -> "HistoryPage":
        """从 history/cursor 接口的 data 字段构造。"""
        cursor = data.get("cursor") or {}
        items = []
        for h in data.get("list") or []:
            stat = h.get("history") or {}
            business = stat.get("business", "")
            item = HistoryItem(
                oid=stat.get("oid", 0),
                business=business,
                view_at=h.get("view_at", 0),
                raw=h,
            )
            if business == "archive":
                item.bvid = stat.get("bvid", "")
                item.progress = h.get("progress", 0)
                item.duration = h.get("duration", 0)
            items.append(item)
        return cls(
            items=items,
            has_more=bool(cursor.get("has_more")),
            max=cursor.get("max", 0),
            business=cursor.get("business", ""),
            view_at=cursor.get("view_at", 0),
        )
