"""
直播相关的接口 URL。

对应 BAC 文档「直播」章节：房间信息、最近弹幕、弹幕服务器信息、发送弹幕。
注意：gethistory 与 getDanmuInfo 实测必须带 WBI 签名（否则 gethistory 静默返回空、
getDanmuInfo 直接 -352 风控），调用方需自行 get_wbi(params)。
"""

from src.config.constants import LIVE_BASE


class LiveUrls:
    """直播间信息与弹幕相关接口。"""

    ROOM_INFO = f"{LIVE_BASE}/room/v1/Room/get_info"  # 房间信息（支持长短号，免登录）
    DANMU_HISTORY = f"{LIVE_BASE}/xlive/web-room/v1/dM/gethistory"  # 最近弹幕（需 WBI，仅最近约 10 条）
    DANMU_INFO = f"{LIVE_BASE}/xlive/web-room/v1/index/getDanmuInfo"  # 弹幕服务器列表与 token（需 WBI）
    SEND_DANMU = f"{LIVE_BASE}/msg/send"  # 发送弹幕（需登录，csrf=bili_jct）
