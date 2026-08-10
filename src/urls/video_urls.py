"""
视频相关的接口 URL。
原 `src/video.py` 中的 `VideoUrls` 迁移并补全至此。
"""

from src.config.constants import API_BASE, WEB_BASE


class VideoUrls:
    """视频信息、播放流、标签、快照等接口。"""

    # 固定端点（无路径参数）
    PLAY = f"{API_BASE}/x/player/wbi/playurl"  # 视频下载（DASH 流）
    VIEW = f"{API_BASE}/x/web-interface/view"  # 视频信息
    VIEW_DETAIL = f"{API_BASE}/x/web-interface/view/detail"  # 视频详细信息
    TAG = f"{API_BASE}/x/tag/archive/tags"  # 视频标签
    CARD = f"{API_BASE}/x/web-interface/card"  # up主信息(简略)
    PAGELIST = f"{API_BASE}/x/player/pagelist"  # 分 P 列表 / cid
    VIDEO_SHOT = f"{API_BASE}/x/player/videoshot"  # 视频快照

    # 点赞/投币/收藏状态
    USER_ACTION_LIKE = f"{API_BASE}/x/web-interface/archive/has/like"  # 是否点赞
    USER_ACTION_COIN = f"{API_BASE}/x/web-interface/archive/coins"  # 投币信息
    USER_ACTION_FAV = f"{API_BASE}/x/v2/fav/video/favoured"  # 是否收藏

    @staticmethod
    def video(bvid: str) -> str:
        """视频播放页链接。"""
        return f"{WEB_BASE}/video/{bvid}"
