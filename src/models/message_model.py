"""私信导出相关的数据模型。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class MessageExportResult:
    """一次私信导出的落盘结果。"""

    export_dir: Path  # 单聊为好友目录；全部导出为 output/message/{我的mid}
    conversation_dirs: list[Path] = field(default_factory=list)  # 本次写入的会话目录
    json_path: Optional[Path] = None  # 单聊的 messages.json；全部导出为 None
    markdown_path: Optional[Path] = None  # 单聊的 messages.md；全部导出为 None
    conversation_count: int = 0  # 成功写入的会话数
    message_count: int = 0  # 这些会话同步后的消息总数
    new_message_count: int = 0  # 本次新增的消息数（force=True 时为全量）
    talker_id: Optional[int] = None  # 单聊对象 mid；全部导出为 None
    truncated: bool = False  # 是否因 max_num 未导出全部会话
    forced: bool = False  # 是否使用了 force 全量刷新
    errors: list[str] = field(default_factory=list)  # 部分会话失败时的摘要
