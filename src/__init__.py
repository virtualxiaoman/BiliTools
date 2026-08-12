"""
BiliTools：py 操控 bilibili 的小工具（后端 SDK）。

重构后目录结构：
- `src/api`        统一请求层（BiliSession）、签名（auth）、异常（errors）
- `src/config`     路径锚点（path）、常量（constants）、Cookie（cookie）
- `src/models`     业务数据模型（dataclass）
- `src/services`   业务服务（获取信息/下载/登录/历史/评论/私信等）
- `src/urls`       API URL 统一管理
- `src/util`       BV/AV 转换、文件名、下载工具

[快速上手]
    from src.services import VideoService

    service = VideoService()  # 使用默认 cookie
    info = service.fetch_info("BV1ov42117yC")
    service.download_video_with_audio("BV1ov42117yC")
"""

from src.services import (
    ArchiveService,
    ContractService,
    FavService,
    HistoryService,
    LoginService,
    MessageService,
    RankService,
    ReplyService,
    UserService,
    VideoService,
)

__version__ = "2.0.0"

__all__ = [
    "ArchiveService",
    "ContractService",
    "FavService",
    "HistoryService",
    "LoginService",
    "MessageService",
    "RankService",
    "ReplyService",
    "UserService",
    "VideoService",
]
