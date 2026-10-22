"""
私信相关的接口 URL。
原 `src/message.py` 中的私信接口迁移至此。
"""

from src.config.constants import API_VC_BASE


class MessageUrls:
    """私信接口。"""

    SEND_MSG = f"{API_VC_BASE}/web_im/v1/web_im/send_msg"  # 发送私信
    GET_SESSIONS = f"{API_VC_BASE}/session_svr/v1/session_svr/get_sessions"  # 会话列表
    FETCH_SESSION_MSGS = f"{API_VC_BASE}/svr_sync/v1/svr_sync/fetch_session_msgs"  # 历史私信
