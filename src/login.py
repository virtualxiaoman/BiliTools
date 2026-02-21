import os
import re
import time

import qrcode
import requests

from src.config import UserAgent, Config


# b站登录(目前能获取登录状态以及扫码登录)
# todo buvid3的获取暂时没有实现，https://github.com/SocialSisterYi/bilibili-API-collect/issues/795中有相关讨论
# todo 获取视频点赞、投币等信息的接口可能是https://api.bilibili.com/x/web-interface/archive/relation?aid=589849008&bvid=BV1nq4y1S7s3
class BiliLogin:
    def __init__(self, headers=None):
        """
        :param headers: 比如headers={"Cookie": cookies().bilicookie, "User-Agent": useragent().pcChrome}
        """
        if headers is not None:
            self.headers = headers
        else:
            self.headers = {"User-Agent": UserAgent().pcChrome}
        self.login_state_url = 'https://api.bilibili.com/x/web-interface/nav'
        self.qr_generate_url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/generate'
        self.qr_login_url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/poll'

        self.login_msg = None

    def get_login_state(self):
        """
        获取登录状态
        [使用方法]:
            BiliLogin(headers).get_login_state()
        :return: 登录信息。使用login_msg["data"]["isLogin"]可获取登录状态
        """
        # get请求https://api.bilibili.com/x/web-interface/nav，参数是cookie，返回的是用户的信息
        r = requests.get(url=self.login_state_url, headers=self.headers)
        login_msg = r.json()
        if login_msg["code"] == 0:
            print("[BiliLogin-get_login_state]登录成功")  # 亦可使用login_msg["data"]["isLogin"])
        else:
            print(f"[BiliLogin-get_login_state]未登录，错误码code={login_msg['code']}")
        self.login_msg = login_msg
        return self.login_msg

    def get_mid(self):
        """
        获取用户UID/mid
        :return: 用户UID/mid
        """
        if self.login_msg is None or self.login_msg["code"] != 0:
            self.get_login_state()  # 如果之前没有获取过登录状态，或者上次获取登录状态失败，则先获取登录状态
        if self.login_msg["code"] == 0:
            mid = self.login_msg["data"]["mid"]
            print(f"[BiliLogin-get_mid]用户UID(mid): {mid}")
            return mid
        else:
            print(f"[BiliLogin-get_mid]未登录，无法获取用户UID/mid，错误码code={self.login_msg['code']}")
            return None

    def get_uname(self):
        """
        获取用户名
        :return: 用户名
        """
        if self.login_msg is None or self.login_msg["code"] != 0:
            self.get_login_state()  # 如果之前没有获取过登录状态，或者上次获取登录状态失败，则先获取登录状态
        if self.login_msg["code"] == 0:
            uname = self.login_msg["data"]["uname"]
            print(f"[BiliLogin-get_uname]用户名: {uname}")
            return uname
        else:
            print(f"[BiliLogin-get_uname]未登录，无法获取用户名，错误码code={self.login_msg['code']}")
            return None

    def qr_login(self, full_path=Config.COOKIE_PATH, img_show=True):
        """
        扫码登录
        [Warning]:
            请妥善保管cookie的路径，本方法只会保存一份cookie到本地的指定路径里
        [使用方法-扫码登录，指定自定义保存cookie的路径，然后检查登录状态]:
            full_path = 'cookie/cookie_大号.txt'  # 这里只是为了展示更改路径，实际使用时仍然建议使用默认路径cookie/qr_login.txt
            biliL = BiliLogin()
            biliL.qr_login(full_path=full_path)  # 扫码登录
            headers = {
                "User-Agent": useragent().pcChrome,
                "Cookie": cookies(path=full_path).bilicookie,
                'referer': "https://www.bilibili.com"
            }
            BiliLogin(headers).get_login_state()  # 检查登录状态
        [使用方法-扫码登录并发送赛博评论]:
            biliL = BiliLogin()
            biliL.qr_login()
            headers = {
                "User-Agent": useragent().pcChrome,
                "Cookie": cookies(path='cookie/qr_login.txt').bilicookie,
                'referer': "https://www.bilibili.com"
            }
            BiliLogin(headers).get_login_state()
            biliR = biliReply(bv="BV1ov42117yC")
            biliR.send_reply("可爱的白州梓！[喜欢]")
        [Tips]:
            登录成功后，返回的是一个字典，其中data中的url是登录成功后的url，其中包含了cookie，例如：
            {'code': 0, 'message': '0', 'ttl': 1, 'data': {'url': 'https://passport.biligame.com/x/passport-login/web/crossDomain?DedeUserID=506925078&DedeUserID__ckMd5=157f54a3efcc1f6c&Expires=1733319655&SESSDATA=11bc6725,1733319655,e4356*61CjDhRqoVMl0n2ynNcVvmXJrOhesGXjqQKrGumPdjqKAVvMseIyvmg43VBwn8PPi7-9kSVmFNM1pxYWYzYVU3NjBsOVVZcVZjYl9IaWd4M0VfZG5kbjU0M2hyLWROdXZ3NE4wMkx0S0Y2Y2o2b1VqeU5hZG14UmdIYjNiZzFhaU11MXZMOFdCWGJBIIEC&bili_jct=4b531e9662a4488573d0ff255f065963&gourl=https%3A%2F%2Fwww.bilibili.com&first_domain=.bilibili.com', 'refresh_token': '43a6c19b5c0e17b419fde286f3328f61', 'timestamp': 1717767655580, 'code': 0, 'message': ''}}
        [文档]:
            https://socialsisteryi.github.io/bilibili-API-collect/docs/login/login_action/QR.html
        :param full_path: cookie的全路径名称(含路径、文件名、后缀)，指定此参数时，其余与cookie路径相关的信息均失效
        :param img_show: 是否立刻用本地的图片查看器打开二维码，默认为True，便于调试扫码
        :return: 登录成功返回True
        """
        # 1. 生成二维码链接
        r = requests.get(self.qr_generate_url, headers=self.headers)
        data = r.json()
        if data['code'] == 0:
            qrcode_key = data['data']['qrcode_key']
            url = data['data']['url']
        else:
            raise Exception('Failed to generate QR code: ' + data.get('message', ''))

        # 2. 准备要保存的目录和文件名，并确保目录存在
        dirname = os.path.dirname(full_path) or "."
        base_name = os.path.splitext(os.path.basename(full_path))[0]
        qr_img_path = os.path.join(dirname, base_name + ".png")
        if not os.path.exists(dirname):
            os.makedirs(dirname, exist_ok=True)
            print(f"[BiliLogin-qr_login]目录 {os.path.abspath(dirname)} 不存在，已创建。")

        # 3. 生成并保存二维码图片
        qr = qrcode.QRCode()
        qr.add_data(url)
        qr.make()
        img = qr.make_image()
        img.save(qr_img_path)
        if img_show:
            img.show()
        print(f"请扫描二维码登录，二维码已保存在 {os.path.abspath(qr_img_path)}")

        start_time = time.time()
        while True:
            r = requests.get(self.qr_login_url, params={'qrcode_key': qrcode_key}, headers=self.headers)
            data = r.json()
            # print(data)
            code = data.get('data', {}).get('code')
            if code == 86101:
                print('[BiliLogin-qr_login]未扫码')
            elif code == 86038:
                print('[BiliLogin-qr_login]二维码失效')
            elif code == 86090:
                print('[BiliLogin-qr_login]扫码成功但未确认')
            elif code == 0:
                print('[BiliLogin-qr_login]登录成功')
                get_cookie = r.headers['set-cookie']
                self._save_cookie(get_cookie, full_path)
                return True
            else:
                print('[BiliLogin-qr_login]未知错误', data)
            if time.time() - start_time > 60:
                print('[BiliLogin-qr_login]超过一分钟，返回False')
                return False
            time.sleep(1)

    def _save_cookie(self, cookie, full_path="./assets/cookie/qr_login.txt"):
        """
        保存cookie
        :param cookie: 原始cookie
        :param full_path: 全路径名称(含路径、文件名、后缀)，指定此参数时，其余与路径相关的信息均失效
        """
        dirname = os.path.dirname(full_path) or "."
        if not os.path.exists(dirname):
            os.makedirs(dirname, exist_ok=True)
            print(f"[BiliLogin-_save_cookie]目录 {os.path.abspath(dirname)} 不存在，已创建。")

        file_path = full_path
        # if full_path is not None:
        #     # 检查路径是否存在，不存在则创建
        #     dirname = os.path.dirname(full_path)
        #     if not os.path.exists(dirname):
        #         os.makedirs(os.path.dirname(full_path))
        #         print(f"full_path{full_path}中的目录不存在，已创建目录。绝对路径为: {os.path.abspath(dirname)}")
        #     file_path = full_path
        # else:
        #     if not os.path.exists(save_path):
        #         os.makedirs(save_path)
        #         print(f"save_path: {save_path} 不存在，已创建。绝对路径为: {os.path.abspath(save_path)}")
        #     file_path = os.path.join(save_path, f"{save_name}.txt")  # 使用os.path.join()连接保存路径和文件名
        # 将cookie存入 [×]此方法会导致部分鉴权参数无法被识别
        # cookie_pairs = cookie.split(", ")
        # cookies_dict = {}
        # for pair in cookie_pairs:
        #     key, value = pair.split("=")
        #     cookies_dict[key] = value
        # cookie_string = "; ".join([f"{key}={value}" for key, value in cookies_dict.items()])
        # 使用正则表达式匹配
        # 找到cookie中的SESSDATA和bili_jct
        try:
            pattern_SESSDATA = re.compile(r"SESSDATA=(.*?);")
            pattern_bili_jct = re.compile(r"bili_jct=(.*?);")
            pattern_DedeUserID = re.compile(r"DedeUserID=(.*?);")
            pattern_DedeUserID__ckMd5 = re.compile(r"DedeUserID__ckMd5=(.*?);")
            pattern_sid = re.compile(r"sid=(.*?);")
            SESSDATA = re.search(pattern_SESSDATA, cookie).group(1)
            bili_jct = re.search(pattern_bili_jct, cookie).group(1)
            DedeUserID = re.search(pattern_DedeUserID, cookie).group(1)
            DedeUserID__ckMd5 = re.search(pattern_DedeUserID__ckMd5, cookie).group(1)
            sid = re.search(pattern_sid, cookie).group(1)
            cookie_string = (f"SESSDATA={SESSDATA}; bili_jct={bili_jct}; DedeUserID={DedeUserID}; "
                             f"DedeUserID__ckMd5={DedeUserID__ckMd5}; sid={sid}")
        except Exception as e:
            # 如果正则提取失败，则降级为直接写入原始 cookie（适用于格式不同的情况）
            print(f"[BiliLogin-_save_cookie]正则解析 cookie 失败: {e}，将原始 cookie 写入文件以便调试")
            cookie_string = cookie or ""

        with open(file_path, "w", encoding="utf-8") as file:
            file.write(cookie_string)
            print(f"[BiliLogin-_save_cookie]cookie已保存在{file_path}")
