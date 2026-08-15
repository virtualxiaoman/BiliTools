"""账号模型：多账号映射表条目（accounts.json 的每一项）。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Account:
    """B 站账号映射表条目。

    :param mid: B站 uid，唯一键
    :param user_name: 昵称，UI 展示用（用户大概率记不住自己的 mid）
    :param cookie_path: 该账号 cookie 文件绝对路径（映射表显式记录，默认在全局 cookie 目录下）
    """

    mid: int
    user_name: str
    cookie_path: Path
