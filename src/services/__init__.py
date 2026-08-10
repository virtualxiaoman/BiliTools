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
"""

from src.services.archive import ArchiveService
from src.services.fav import FavService
from src.services.history import HistoryService
from src.services.login import LoginService
from src.services.message import MessageService
from src.services.rank import RankService
from src.services.reply import ReplyService
from src.services.user import ContractService, UserService
from src.services.video import VideoService

__all__ = [
    "ArchiveService",
    "FavService",
    "HistoryService",
    "LoginService",
    "MessageService",
    "RankService",
    "ReplyService",
    "ContractService",
    "UserService",
    "VideoService",
]
