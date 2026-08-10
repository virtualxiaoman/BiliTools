"""
数据模型层：dataclass 定义的业务数据对象（视频信息、用户信息、历史记录等）。

模块命名：`*_model.py`，与 services / urls 下的同名文件区分。
- `video_model.py`   VideoInfo / VideoStat / VideoOwner / VideoUserAction 等
- `user_model.py`    UserInfo
- `download_model.py` VideoQuality / DownloadResult / DASH 流数据
"""

from src.models.download_model import AudioStream, DashStreams, DownloadResult, VideoQuality, VideoStream
from src.models.fav_model import FavInfo
from src.models.login_model import LoginUser
from src.models.video_model import (
    VideoInfo,
    VideoOwner,
    VideoPage,
    VideoSeason,
    VideoSeasonEpisode,
    VideoStat,
    VideoUserAction,
)
from src.models.user_model import UserInfo

__all__ = [
    "AudioStream",
    "DashStreams",
    "DownloadResult",
    "VideoQuality",
    "VideoStream",
    "FavInfo",
    "LoginUser",
    "VideoInfo",
    "VideoOwner",
    "VideoPage",
    "VideoSeason",
    "VideoSeasonEpisode",
    "VideoStat",
    "VideoUserAction",
    "UserInfo",
]
