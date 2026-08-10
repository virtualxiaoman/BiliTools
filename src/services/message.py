"""
私信服务：发送私信。
取代旧 `src/message.py` 的 `BiliMessage`，使用统一 BiliSession + 异常体系。
"""

import json
import logging
from typing import Optional

from src.api.auth import get_dev_id, get_timestamp
from src.api.session import BiliSession
from src.config.cookie import BiliCookies
from src.services.login import LoginService
from src.urls.message_urls import MessageUrls

logger = logging.getLogger(__name__)


class MessageService:
    """B 站私信服务。"""

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    def send_msg(self, receiver_uid: int, content: str,
                 sender_uid: Optional[int] = None, msg_type: int = 1) -> dict:
        """发送私信。

        :param receiver_uid: 接收者mid
        :param content: 内容
        :param sender_uid: 发送者mid，为空时自动使用本地默认登录账号的mid
        :param msg_type: 消息类型。1:发送文字 2:发送图片 5:撤回消息
        :return: 接口返回的 data 字典
        """
        if sender_uid is None:
            sender_uid = LoginService(self.session).get_mid()
            if sender_uid is None:
                raise ValueError("未登录，无法自动获取发送者mid，请指定 sender_uid 参数")

        # 设备id(这个参数我大号是B182F410-3865-46ED-840F-B58B71A78B5E，小号是281ED237-9433-4BF5-BECC-D00AC88E69BF，
        # 但是换过来也能用，估计这个参数不严格)
        dev_id = get_dev_id()
        timestamp = get_timestamp()  # 时间戳（秒）
        data = {
            'msg[sender_uid]': sender_uid,
            'msg[receiver_id]': receiver_uid,
            'msg[receiver_type]': 1,  # 固定为1
            'msg[msg_type]': msg_type,
            'msg[msg_status]': 0,  # 固定为0
            'msg[content]': json.dumps({"content": content}),  # 使用 json.dumps() 将内容转换为 JSON 格式字符串
            'msg[timestamp]': timestamp,
            'msg[dev_id]': dev_id,
            'csrf': BiliCookies.from_file().bili_jct or "",
        }
        return self.session.post(MessageUrls.SEND_MSG, data=data)
