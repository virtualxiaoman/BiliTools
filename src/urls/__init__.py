"""
URL 统一管理：按业务域分组。

规则：
- 无路径参数的固定端点 → 类常量（拼接基础域名）；
- 需要路径/参数拼接的端点 → 静态方法。

模块命名：`*_urls.py`，与 services / models 下的同名文件区分。
基础域名常量见 `src/config/constants.py`。
"""

from src.urls.video_urls import VideoUrls
from src.urls.user_urls import UserUrls
from src.urls.login_urls import LoginUrls
from src.urls.history_urls import HistoryUrls
from src.urls.rank_urls import RankUrls
from src.urls.comment_urls import CommentUrls
from src.urls.message_urls import MessageUrls
from src.urls.fav_urls import FavUrls
from src.urls.archive_urls import ArchiveUrls
from src.urls.contract_urls import ContractUrls
from src.urls.emote_urls import EmoteUrls
from src.urls.garb_urls import GarbUrls

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
    "EmoteUrls",
    "GarbUrls",
]
