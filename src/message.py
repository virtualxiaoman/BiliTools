import json

import requests

from src.config import UserAgent, BiliCookies as Cookies
from src.utils import AuthUtil
from src.login import BiliLogin


# b站私信(目前已实现发送私信功能)
class BiliMessage:
    def __init__(self):
        self.headers = {
            "User-Agent": UserAgent().pcChrome,
            "Cookie": Cookies().bilicookie,
            'referer': 'https://message.bilibili.com/'
        }
        self.url_send_msg = 'https://api.vc.bilibili.com/web_im/v1/web_im/send_msg'

    def send_msg(self, receiver_uid, content, sender_uid=None, msg_type=1):
        """
        发送私信
        [使用方法]
            biliM = biliMessage()
            biliM.send_msg(receiver_uid=381978872, content="你好，请问是千年的爱丽丝同学吗？")
        :param sender_uid: 发送者mid，为空时自动使用本地默认登录账号的mid
        :param receiver_uid: 接收者mid
        :param content: 内容
        :param msg_type: 消息类型。1:发送文字 2:发送图片 5:撤回消息
        :return:
        """
        if sender_uid is None:
            bililogin = BiliLogin(self.headers)
            sender_uid = bililogin.get_mid()
            sender_uname = bililogin.get_uname()
            print(f"发送者mid未指定，已自动使用本地默认登录账号，发送者mid={sender_uid}，用户名为{sender_uname}")

        # 设备id(这个参数我大号是B182F410-3865-46ED-840F-B58B71A78B5E，小号是281ED237-9433-4BF5-BECC-D00AC88E69BF，
        # 但是换过来也能用，估计这个参数不严格)
        dev_id = AuthUtil.get_dev_id()
        timestamp = AuthUtil.get_timestamp()  # 时间戳（秒）
        data = {
            'msg[sender_uid]': sender_uid,
            'msg[receiver_id]': receiver_uid,
            'msg[receiver_type]': 1,  # 固定为1
            'msg[msg_type]': msg_type,
            'msg[msg_status]': 0,  # 固定为0
            'msg[content]': json.dumps({"content": content}),  # 使用 json.dumps() 将内容转换为 JSON 格式字符串
            'msg[timestamp]': timestamp,
            # 'msg[new_face_version]': 0,  # 目前测出来的有0或1，带免费表情的时候是1，付费的我没有。
            'msg[dev_id]': dev_id,
            # 'from_firework': '0',
            # 'build': '0',
            # 'mobi_app': 'web',
            # 'csrf_token': cookies().bili_jct,
            'csrf': Cookies().bili_jct
        }
        r = requests.post(self.url_send_msg, data=data, headers=self.headers)
        r_json = r.json()
        if r_json['code'] == 0:
            msg_content = r_json['data']['msg_content']
            content_dict = json.loads(msg_content)
            content_value = content_dict['content']
            print(f"发送成功，消息内容：{content_value}")
        else:
            print(f"发送失败，错误码{r_json['code']}，错误信息：{r_json}")
