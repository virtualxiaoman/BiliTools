import requests

from src.config import UserAgent, BiliCookies as cookies
from src.login import BiliLogin
from src.utils import BV2AV


# b站评论相关操作(目前已实现发布评论功能， todo: 爬取评论)
class BiliReply:
    """暂时只支持视频评论"""

    def __init__(self, bv=None, av=None):
        """
        :param bv: bv号(bv号和av号有且只能有一个不为None)
        :param av: av号(bv号和av号有且只能有一个不为None)
        """
        self.bv = bv
        self.headers = {
            "User-Agent": UserAgent().pcChrome,
            "Cookie": cookies().bilicookie,
            'referer': f'https://www.bilibili.com/video/{self.bv}'
        }
        if av is None:
            if self.bv is None:
                raise ValueError("bv和av不能同时为None")
            else:
                self.av = BV2AV().bv2av(self.bv)
        else:
            self.av = av

    def send_reply(self, message):
        """
        [使用方法]:
            biliR = biliReply(bv="BV141421X7TZ")
            biliR.send_reply("对着香奶妹就是一个冲刺😋")
        :param message: 评论内容
        """
        # 对https://api.bilibili.com/x/v2/reply/add发送POST请求，参数是type=1，oid=self.av，message=评论内容，plat=1
        post_url = "https://api.bilibili.com/x/v2/reply/add"
        post_data = {
            "type": 1,
            "oid": self.av,
            "message": message,
            "plat": 1,
            "csrf": cookies().bili_jct  # CSRF Token是cookie中的bili_jct
        }
        r = requests.post(url=post_url, headers=self.headers, data=post_data)
        reply_data = r.json()
        if reply_data["code"] != 0:
            print(f"评论失败，错误码{reply_data['code']}，"
                  f"请查看'https://socialsisteryi.github.io/bilibili-API-collect/docs/comment/action.html'获取错误码信息")
            BiliLogin(self.headers).get_login_state()
        else:
            print("评论成功")
            print("评论rpid：", reply_data["data"]["rpid"])
            print("评论内容：", reply_data["data"]["reply"]["content"]["message"])
