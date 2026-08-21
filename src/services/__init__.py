"""
业务服务层：面向业务场景的封装（获取信息、下载、登录、历史记录等）。

- `video.py`    VideoService：视频信息 / 下载
- `login.py`    LoginService：扫码登录
- `history.py`  HistoryService：历史记录
- `user.py`     UserService / ContractService
- `reply.py`    ReplyService：评论
- `message.py`  MessageService：私信
- `rank.py`     RankService：排行榜
- `fav.py`      FavService：收藏夹
- `archive.py`  ArchiveService：合集
- `emote.py`    EmoteService：收藏表情包
- `garb.py`     GarbService：收藏集 / 装扮素材
- `dressup.py`  DressupService：装扮页签统一搜索与批量下载
"""

from src.services.archive import ArchiveService
from src.services.dressup import DressupService
from src.services.emote import EmoteService
from src.services.fav import FavService
from src.services.garb import GarbService
from src.services.history import HistoryService
from src.services.login import LoginService
from src.services.message import MessageService
from src.services.rank import RankService
from src.services.reply import ReplyService
from src.services.user import ContractService, UserService
from src.services.video import VideoService

__all__ = [
    "ArchiveService",
    "DressupService",
    "EmoteService",
    "FavService",
    "GarbService",
    "HistoryService",
    "LoginService",
    "MessageService",
    "RankService",
    "ReplyService",
    "ContractService",
    "UserService",
    "VideoService",
]
