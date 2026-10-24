"""评论导出相关的数据模型。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommentExportResult:
    """一次视频评论导出的落盘结果。"""

    export_dir: Path  # output/comments/{bvid}
    json_path: Path  # comments.json（完整评论树）
    markdown_path: Path  # comments.md（人读）
    bvid: str = ""
    aid: int = 0
    sort: str = ""  # latest / hot
    root_count: int = 0  # 根评论数（含置顶）
    sub_count: int = 0  # 楼中楼总数
    pinned_count: int = 0  # 置顶评论数
    fetched_at: str = ""  # 北京时间 ISO 字符串
