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
- `dynamic.py`  DynamicService：动态（opus）解析与下载
- `live.py`     LiveService：直播间信息 / 最近弹幕 / 实时弹幕监听录制 / 发送弹幕
- `tts.py`      TtsService：GPT-SoVITS 语音合成客户端（本机 HTTP）
- `live_speech.py` LiveSpeechService：弹幕 → 过滤 → 队列 → 合成 → 播放
"""

from src.services.archive import ArchiveService
from src.services.dressup import DressupService
from src.services.dynamic import DynamicService
from src.services.emote import EmoteService
from src.services.fav import FavService
from src.services.garb import GarbService
from src.services.history import HistoryService
from src.services.live import LiveService
from src.services.live_speech import LiveSpeechService, SpeechFilter
from src.services.login import LoginService
from src.services.message import MessageService
from src.services.rank import RankService
from src.services.reply import ReplyService
from src.services.tts import TtsService
from src.services.user import ContractService, UserService
from src.services.video import VideoService

__all__ = [
    "ArchiveService",
    "DressupService",
    "DynamicService",
    "EmoteService",
    "FavService",
    "GarbService",
    "HistoryService",
    "LiveService",
    "LiveSpeechService",
    "SpeechFilter",
    "TtsService",
    "LoginService",
    "MessageService",
    "RankService",
    "ReplyService",
    "ContractService",
    "UserService",
    "VideoService",
]
