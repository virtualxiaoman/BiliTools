"""
数据模型层：dataclass 定义的业务数据对象（视频信息、用户信息、历史记录等）。

M0/M1 阶段先建立包骨架，M2 起逐步填充：
- `video.py`   VideoInfo / VideoStat / VideoOwner / VideoUserAction 等
- `user.py`    UserInfo
- `download.py` VideoQuality / DownloadResult / DASH 流数据
"""

from src.models.download import AudioStream, DashStreams, DownloadResult, VideoQuality, VideoStream
from src.models.login import LoginUser
from src.models.video import (
    VideoInfo,
    VideoOwner,
    VideoPage,
    VideoSeason,
    VideoSeasonEpisode,
    VideoStat,
    VideoUserAction,
)
from src.models.user import UserInfo

__all__ = [
    "AudioStream",
    "DashStreams",
    "DownloadResult",
    "VideoQuality",
    "VideoStream",
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
