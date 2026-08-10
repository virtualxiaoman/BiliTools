"""
私信相关的接口 URL。
原 `src/message.py` 中的私信接口迁移至此。
"""

from src.config.constants import API_VC_BASE


class MessageUrls:
    """私信接口。"""

    SEND_MSG = f"{API_VC_BASE}/web_im/v1/web_im/send_msg"  # 发送私信
