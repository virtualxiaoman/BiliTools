"""
URL 统一管理：按业务域分组。

规则：
- 无路径参数的固定端点 → 类常量（拼接基础域名）；
- 需要路径/参数拼接的端点 → 静态方法。

基础域名常量见 `src/config/constants.py`。
"""

from src.urls.video import VideoUrls
from src.urls.user import UserUrls
from src.urls.login import LoginUrls
from src.urls.history import HistoryUrls
from src.urls.rank import RankUrls
from src.urls.comment import CommentUrls
from src.urls.message import MessageUrls
from src.urls.fav import FavUrls
from src.urls.archive import ArchiveUrls
from src.urls.contract import ContractUrls

__all__ = [
    "VideoUrls",
    "UserUrls",
    "LoginUrls",
    "HistoryUrls",
    "RankUrls",
    "CommentUrls",
    "MessageUrls",
    "FavUrls",
    "ArchiveUrls",
    "ContractUrls",
]
