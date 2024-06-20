import re
import json
import time
import pandas as pd
import requests
import os
import warnings
from PIL import Image
from io import BytesIO
import random
import qrcode

from Tools.util.Colorful_Console import ColoredText as CT  # 用于控制台的彩色输出
from Tools.bili_util import BV2AV  # BV号和AV号的转换
from Tools.bili_util import AuthUtil  # 获取鉴权参数
from Tools.bili_util import BiliVideoUtil  # B站视频工具
from Tools.config import useragent  # User-Agent
from Tools.config import bilicookies as cookies  # B站cookie
from Tools.config import Config  # 加载配置信息
cf = Config()

# b站登录(目前能获取登录状态以及扫码登录)
class biliLogin:
    def __init__(self, headers=None):
        """
        :param headers: 比如headers={"Cookie": cookies().bilicookie, "User-Agent": useragent().pcChrome}
        """
        if headers is not None:
            self.headers = headers
        else:
            self.headers = {"User-Agent": useragent().pcChrome}
        self.login_state_url = 'https://api.bilibili.com/x/web-interface/nav'
        self.qr_generate_url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/generate'
        self.qr_login_url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/poll'

    def get_login_state(self):
        """
        获取登录状态
        [使用方法]:
            biliLogin(headers).get_login_state()
        :return: 登录信息。使用login_msg["data"]["isLogin"]可获取登录状态
        """
        # get请求https://api.bilibili.com/x/web-interface/nav，参数是cookie，返回的是用户的信息
        r = requests.get(url=self.login_state_url, headers=self.headers)
        login_msg = r.json()
        if login_msg["code"] == 0:
            print("[biliLogin-get_login_state]登录成功")  # 亦可使用login_msg["data"]["isLogin"])
        else:
            print("[biliLogin-get_login_state]未登录")
        return login_msg

    def qr_login(self, save_path="cookie", save_name="qr_login", img_show=True):
        """
        扫码登录
        [Warning]:
            请妥善保管cookie的路径，本方法只会保存一份cookie到本地的指定路径里
        [使用方法-扫码登录并检查登录状态]:
            biliL = biliLogin()
            biliL.qr_login()  # 扫码登录
            headers = {
                "User-Agent": useragent().pcChrome,
                "Cookie": cookies(path='cookie/qr_login.txt').bilicookie,
                'referer': "https://www.bilibili.com"
            }
            biliLogin(headers).get_login_state()  # 检查登录状态
        [使用方法-扫码登录并发送赛博评论]:
            biliL = biliLogin()
            biliL.qr_login()
            headers = {
                "User-Agent": useragent().pcChrome,
                "Cookie": cookies(path='cookie/qr_login.txt').bilicookie,
                'referer': "https://www.bilibili.com"
            }
            biliLogin(headers).get_login_state()
            biliR = biliReply(bv="BV1ov42117yC")
            biliR.send_reply("可爱的白州梓！[喜欢]")
        [Tips]:
            登录成功后，返回的是一个字典，其中data中的url是登录成功后的url，其中包含了cookie，例如：
            {'code': 0, 'message': '0', 'ttl': 1, 'data': {'url': 'https://passport.biligame.com/x/passport-login/web/crossDomain?DedeUserID=506925078&DedeUserID__ckMd5=157f54a3efcc1f6c&Expires=1733319655&SESSDATA=11bc6725,1733319655,e4356*61CjDhRqoVMl0n2ynNcVvmXJrOhesGXjqQKrGumPdjqKAVvMseIyvmg43VBwn8PPi7-9kSVmFNM1pxYWYzYVU3NjBsOVVZcVZjYl9IaWd4M0VfZG5kbjU0M2hyLWROdXZ3NE4wMkx0S0Y2Y2o2b1VqeU5hZG14UmdIYjNiZzFhaU11MXZMOFdCWGJBIIEC&bili_jct=4b531e9662a4488573d0ff255f065963&gourl=https%3A%2F%2Fwww.bilibili.com&first_domain=.bilibili.com', 'refresh_token': '43a6c19b5c0e17b419fde286f3328f61', 'timestamp': 1717767655580, 'code': 0, 'message': ''}}
        [文档]:
            https://socialsisteryi.github.io/bilibili-API-collect/docs/login/login_action/QR.html
        :param save_path: 保存cookie的路径
        :param save_name: 保存cookie的文件名
        :param img_show: 是否立刻用本地的图片查看器打开二维码，默认为True，便于调试扫码
        :return: 登录成功返回True
        """
        r = requests.get(self.qr_generate_url, headers=self.headers)
        data = r.json()
        if data['code'] == 0:
            qrcode_key = data['data']['qrcode_key']
            url = data['data']['url']
        else:
            raise Exception('Failed to generate QR code: ' + data['message'])
        qr = qrcode.QRCode()
        qr.add_data(url)
        qr.make()
        img = qr.make_image()
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        img.save(f"{save_path}/{save_name}.png")
        if img_show:
            img.show()
        print(f"请扫描二维码登录，二维码已保存在{save_path}/{save_name}.png")
        start_time = time.time()
        while True:
            r = requests.get(self.qr_login_url, params={'qrcode_key': qrcode_key}, headers=self.headers)
            data = r.json()
            # print(data)
            if data['data']['code'] == 86101:
                print('[biliLogin-qr_login]未扫码')
            elif data['data']['code'] == 86038:
                print('[biliLogin-qr_login]二维码失效')
            elif data['data']['code'] == 86090:
                print('[biliLogin-qr_login]扫码成功但未确认')
            elif data['data']['code'] == 0:
                print('[biliLogin-qr_login]登录成功')
                get_cookie = r.headers['set-cookie']
                self._save_cookie(get_cookie, save_path, save_name)
                return True
            else:
                print('[biliLogin-qr_login]未知错误')
            elapsed_time = time.time() - start_time
            if elapsed_time > 60:
                print('[biliLogin-qr_login]超过一分钟，返回False')
                return False
            time.sleep(1)

    def _save_cookie(self, cookie, save_path, save_name):
        """
        保存cookie
        :param cookie: 原始cookie
        :param save_path: 保存路径
        :param save_name: 保存文件名
        """
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        file_path = os.path.join(save_path, f"{save_name}.txt")  # 使用os.path.join()连接保存路径和文件名
        # 将cookie存入 [×]此方法会导致部分鉴权参数无法被识别
        # cookie_pairs = cookie.split(", ")
        # cookies_dict = {}
        # for pair in cookie_pairs:
        #     key, value = pair.split("=")
        #     cookies_dict[key] = value
        # cookie_string = "; ".join([f"{key}={value}" for key, value in cookies_dict.items()])
        # 使用正则表达式匹配
        # 找到cookie中的SESSDATA和bili_jct
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
        cookie = f"SESSDATA={SESSDATA}; bili_jct={bili_jct}; DedeUserID={DedeUserID}; " \
                 f"DedeUserID__ckMd5={DedeUserID__ckMd5}; sid={sid}"

        with open(file_path, "w") as file:
            file.write(cookie)


# 获取b站视频信息(目前已实现获取视频信息，下载视频、音频、封面、快照功能)
class biliVideo(BiliVideoUtil):
    def __init__(self, bv=None, av=None, cookie_path=None):
        """
        [使用方法]:
            biliV = biliVideo("BV18x4y187DE")  # [必要]输入bv号
            biliV.get_content()  # [可选]只获取信息，而不下载视频
            biliV.show_values()  # [非必要]显示视频信息
        [Attributes]:
          基本属性：
            bv: bv号
            av: av号
            cid: cid号，鉴权参数
            url_bv: 视频链接
            headers: 请求头
          视频信息：
            rtext: 网页的文本，也就是r.text
            title: 标题
            pic: 封面路径
            desc: 简介
            stat: 统计数据，比如{'aid': 1003283555, 'view': 27847, 'danmaku': 76, 'reply': 143, 'favorite': 1458,
                                'coin': 201, 'share': 40, 'now_rank': 0, 'his_rank': 0, 'like': 1566, 'dislike': 0,
                                'evaluation': '', 'vt': 0, 'viewseo': 27847}
            view: 播放量
            dm: 弹幕量
            reply: 评论量
            time: 发布时间
            like: 点赞量
            coin: 投币量
            fav: 收藏量
            share: 转发量
          额外信息：
            down_video_json: 视频的下载信息（包含视频与音频地址，在download_video()与download_audio()中获取）
          外部存储：
            cookie_path: 本地cookie路径
            [×]html_path: html存储路径，已被废弃

        :param bv: bv号
        :param av: av号
        :param cookie_path: 本地cookie路径。默认为 LOGIN_COOKIE_PATH = "cookie/qr_login.txt"

        """
        # 初始化信息
        super().__init__(bv=bv, av=av)
        if cookie_path is None:
            cookie_path = cf.LOGIN_COOKIE_PATH
            warning_text = "[此警告可忽略] cookie_path参数未指定，默认为 'cookie/qr_login.txt' ，请注意是否是所需要的cookie。"
            modify_tip = '请修改为类似这样的参数传递：cookie_path="cookie/qr_login.txt"'
            warnings.warn(warning_text + "[Tips]: " + modify_tip, stacklevel=1)

        self.url_bv = f"https://www.bilibili.com/video/{self.bv}"
        self.url_play = "https://api.bilibili.com/x/player/wbi/playurl"  # 视频下载信息的获取地址

        self.headers = {
            "User-Agent": useragent().pcChrome,
            "Cookie": cookies(path=cookie_path).bilicookie,
            'referer': self.url_bv
        }

        # 网页文本
        self.rtext = None  # 网页的文本，也就是r.text

        # 基本信息
        self.title = None  # 视频的标题
        self.pic = None  # 视频的封面路径
        self.desc = None  # 视频的简介
        self.stat = None  # 视频的统计数据
        self.view = None  # 视频的播放量
        self.dm = None  # 视频的弹幕量
        self.reply = None  # 视频的评论量
        self.time = None  # 视频的发布时间
        self.like = None  # 视频的点赞量
        self.coin = None  # 视频的投币量
        self.fav = None  # 视频的收藏量
        self.share = None  # 视频的转发量

        # 额外信息
        self.down_video_json = None  # 视频的下载信息

        # 自动调用的方法
        self.get_html()  # 自动获取html

    def get_html(self):
        """
        获取html
        [使用方法]:
            biliV = biliVideo("BV1ov42117yC")
            biliV.get_html()
        :return:
        """
        biliLogin(self.headers).get_login_state()
        r = requests.get(url=self.url_bv, headers=self.headers)
        r.encoding = 'utf-8'
        self.rtext = r.text
        # if self.html_path is not None:
        #     if not os.path.exists(self.html_path):
        #         os.makedirs(self.html_path)
        #     with open(f"{self.html_path}{self.bv}.html", 'w', encoding='utf-8') as f:
        #         f.write(self.rtext)

    def get_content(self):
        """
        [使用方法]:
            biliV = biliVideo("BV18x4y187DE")
            biliV.get_html()  # [必要]获取html
            biliV.get_content()
        不能保证一定能用，获取view,dm的上个月还能用，这个月就不能用了，B站前端牛魔王又改了
        """
        # if self.html_path is not None:
        #     with open(f"{self.html_path}{self.bv}.html", 'r', encoding='utf-8') as f:
        #         self.rtext = f.read()

        pattern_base_data = re.compile(r'window\.__INITIAL_STATE__=(.*?);\(function\(\)')
        base_data_match = re.search(pattern_base_data, self.rtext)

        if base_data_match:
            base_data_content = base_data_match.group(1)
            base_data_content = json.loads(base_data_content)
            aid = base_data_content['videoData']['aid']
            bvid = base_data_content['videoData']['bvid']
            if self.av != aid or self.bv != bvid:
                error_text = f'av:{self.av}，bv:{self.bv}有误。'
                modify_tip = f'请检查其与爬取到的av:{aid}，bv:{bvid}是否一致'
                raise ValueError(error_text + "[Tips:]" + modify_tip)
            self.title = base_data_content['videoData']['title']
            self.pic = base_data_content["videoData"]["pic"]
            self.desc = base_data_content["videoData"]["desc"]
            self.stat = base_data_content["videoData"]["stat"]  # B站牛魔前端又改了
            self.view = self.stat["view"]
            self.dm = self.stat["danmaku"]
            self.reply = self.stat["reply"]
            self.like = self.stat["like"]
            self.coin = self.stat["coin"]
            self.fav = self.stat["favorite"]
            self.share = self.stat["share"]
        else:
            print("爬取基础数据错误，再见ヾ(￣▽￣)")

        # # <div class="view-text" data-v-aed3e268="">2.8万</div>
        # pattern_view_data = re.compile(r'<div class="view-text"[^>]*>(.*?)\s*</div>')
        # view_data_match = re.search(pattern_view_data, self.rtext)
        # if view_data_match:
        #     view_data_content = view_data_match.group(1)
        #     self.view = view_data_content
        # else:
        #     print("爬取播放量数据错误，再见ヾ(￣▽￣)")
        #
        # pattern_dm_data = re.compile(r'<div class="dm-text"[^>]*>(.*?)\s*</div>')
        # dm_data_match = re.search(pattern_dm_data, self.rtext)
        # if dm_data_match:
        #     dm_data_content = dm_data_match.group(1)
        #     self.dm = dm_data_content
        # else:
        #     print("爬取弹幕数据错误，再见ヾ(￣▽￣)")
        #
        # # <span data-v-052ae598="" class="total-reply">143</span>
        # pattern_reply_data = re.compile(r'class="total-reply[^>]*>(.*?)</span>')
        # reply_data_match = re.search(pattern_reply_data, self.rtext)
        # if reply_data_match:
        #     reply_data_content = reply_data_match.group(1)
        #     self.reply = reply_data_content
        # else:
        #     print("爬取评论数据错误，再见ヾ(￣▽￣)")

        pattern_time_data = re.compile(r'<div class="pubdate-ip-text"[^>]*>(.*?)\s*</div>')
        time_data_match = re.search(pattern_time_data, self.rtext)
        if time_data_match:
            time_data_content = time_data_match.group(1)
            self.time = time_data_content
        else:
            print("爬取发布时间数据错误，再见ヾ(￣▽￣)")

        # pattern_like_data = re.compile(r'<span class="video-like-info[^>]*>(.*?)</span>')
        # like_data_match = re.search(pattern_like_data, self.rtext)
        # if like_data_match:
        #     like_data_content = like_data_match.group(1)
        #     self.like = like_data_content
        # else:
        #     print("爬取点赞数据错误，再见ヾ(￣▽￣)")
        #
        # pattern_coin_data = re.compile(r'<span class="video-coin-info[^>]*>(.*?)</span>')
        # coin_data_match = re.search(pattern_coin_data, self.rtext)
        # if coin_data_match:
        #     coin_data_content = coin_data_match.group(1)
        #     self.coin = coin_data_content
        # else:
        #     print("爬取投币数据错误，再见ヾ(￣▽￣)")
        #
        # pattern_fav_data = re.compile(r'<span class="video-fav-info[^>]*>(.*?)</span>')
        # fav_data_match = re.search(pattern_fav_data, self.rtext)
        # if fav_data_match:
        #     fav_data_content = fav_data_match.group(1)
        #     self.fav = fav_data_content
        # else:
        #     print("爬取收藏数据错误，再见ヾ(￣▽￣)")
        #
        # pattern_share_data = re.compile(r'<span class="video-share-info[^>]*>(.*?)</span>')
        # share_data_match = re.search(pattern_share_data, self.rtext)
        # if share_data_match:
        #     share_data_content = share_data_match.group(1)
        #     self.share = share_data_content
        # else:
        #     print("爬取转发数据错误，再见ヾ(￣▽￣)")

    def download_video(self, save_video_path=None, save_video_name=None, full_path=None, qn=80, platform="pc",
                       high_quality=1, fnval=16):
        """
        [使用方法]:
            biliV = biliVideo("BV18x4y187DE")
            biliV.download_video()
        参数具体请查看 `BAC文档
        <https://socialsisteryi.github.io/bilibili-API-collect/docs/video/videostream_url.html>`_.
        :param save_video_path: 视频保存路径。路径为f"{save_video_path}{self.bv}.mp4"。如不指定，则保存在当前目录下f"{self.bv}.mp4"
        :param save_video_name: 视频保存名称。
        :param full_path: 全路径名称(含路径、文件名、后缀)，指定此参数时，其余与路径相关的信息均失效
        :param qn: 视频清晰度。80就是1080p，64就是720p。该值在DASH格式下无效，因为DASH会取到所有分辨率的流地址
        :param platform: 平台。pc或html5
        :param high_quality: 当platform=html5时，此值为1可使画质为1080p
        :param fnval: 1代表mp4，16是DASH。非常建议使用16。
        :return: 下载成功返回True，失败返回False(大部分情况是因为视频不存在)
        """
        self.check_path(save_video_path)
        if self.cid is None:
            return False
        params = {
            "bvid": self.bv,
            "cid": self.cid,
            "qn": qn,
            "fnver": 0,  # 定值
            "fnval": fnval,
            "fourk": 1,  # 是否允许4k。取0代表画质最高1080P（这是不传递fourk时的默认值），取1代表最高4K
            "platform": platform,
            "high_quality": high_quality,
        }
        r = requests.get(url=self.url_play, headers=self.headers, params=params)
        self.down_video_json = r.json()
        # print(self.down_video_json)
        if fnval == 1:
            video_content = requests.get(url=self.down_video_json["data"]["durl"][0]["url"], headers=self.headers).content
        else:
            video_content = requests.get(url=self.down_video_json["data"]["dash"]["video"][0]["baseUrl"],
                                         headers=self.headers).content
        self._save_mp4(video_content, save_video_path, save_video_name, full_path=full_path)
        return True

    def download_audio(self, save_audio_path=None, save_audio_name=None, full_path=None, fnval=16):
        """
        下载音频。如果视频音频都要，建议在download_video之后使用，这样能减少一次请求。
        [使用方法]:
            biliV = biliVideo("BV12a411k7os")
            biliV.download_audio(save_audio_path="output")
        :param save_audio_path: 音频保存路径
        :param save_audio_name: 音频保存名称
        :param full_path: 全路径名称(含路径、文件名、后缀)，指定此参数时，其余与路径相关的信息均失效
        :param fnval: 一般就是16了，原因请见download_video()里fnval参数的描述
        :return: 下载成功返回True，失败返回False(大部分情况是因为音频不存在)
        """
        self.check_path(save_audio_path)
        if self.down_video_json is None:
            if self.cid is None:
                return False
            params = {
                "bvid": self.bv,
                "cid": self.cid,
                "fnval": fnval
            }
            r = requests.get(url=self.url_play, headers=self.headers, params=params)
            self.down_video_json = r.json()
        # print(self.down_video_json)
        audio_content = requests.get(url=self.down_video_json["data"]["dash"]["audio"][0]["baseUrl"],
                                     headers=self.headers).content
        self._save_mp3(audio_content, save_audio_path, save_audio_name, full_path=full_path)
        return True

    def download_video_with_audio(self, auto_remove=True, save_video_path=None, save_video_name=None,
                                  save_audio_path=None, save_audio_name=None,
                                  save_path=None, save_name=None):
        """
        下载视频与音频后合并
        [使用方法]:
            biliV = biliVideo("BV1hi4y1e7B1")
            success = biliV.download_video_with_audio(save_video_path='output', save_audio_path='output', save_path='output')
            if success:
                print("下载成功")
            else:
                print("下载失败")
        :param auto_remove: 是否自动删除视频与音频，默认自动删除
        :param save_video_path: 视频保存路径
        :param save_video_name: 视频保存名称
        :param save_audio_path: 音频保存路径
        :param save_audio_name: 音频保存名称
        :param save_path: 合并后的视频保存路径
        :param save_name: 合并后的视频保存名称
        """
        self.check_path([save_video_path, save_audio_path, save_path])
        video_path = self._get_path(save_video_path, save_video_name, add_desc="视频(无音频)", save_type="mp4")
        audio_path = self._get_path(save_audio_path, save_audio_name, add_desc="音频", save_type="mp3")
        va_path = self._get_path(save_path, save_name, add_desc="视频", save_type="mp4")
        video_state = self.download_video(full_path=video_path)
        audio_state = self.download_audio(full_path=audio_path)
        if video_state and audio_state:
            self.merge_video_audio(video_path, audio_path, va_path)
        else:
            return False
        if auto_remove:
            os.remove(video_path)
            os.remove(audio_path)
        return True

    def download_pic(self, save_pic_path=None, save_pic_name=None, full_path=None):
        """
        图片下载
        [使用方法]
            biliV = biliVideo("BV1Jv4y1p7q3")
            biliV.get_html()
            biliV.get_content()
            biliV.download_pic(save_pic_path="output", save_pic_name="BV1Jv4y1p7q3封面")
        :param save_pic_path: 图片保存路径
        :param save_pic_name: 图片保存名称
        :param full_path: 全路径名称(含路径、文件名、后缀)，指定此参数时，其余与路径相关的信息均失效
        """
        if self.pic is None:
            self.get_content()
        if self.pic is None:
            print("图片地址获取失败，再见ヾ(￣▽￣)")
            return 114514
        print(self.pic)
        pic_content = requests.get(url=self.pic, headers=self.headers).content
        if self.pic.endswith(".png"):
            save_pic_type = "png"
        else:
            save_pic_type = "jpg"
        self._save_pic(pic_content, save_pic_path, save_pic_name, save_type=save_pic_type, full_path=full_path)

    def download_videoshot(self, save_videoshot_path=None, save_videoshot_name=None, index=0):
        """
        视频快照下载
        [使用方法]
            biliv = biliVideo("BV1zm411y7eF")
            biliv.download_videoshot(save_videoshot_path="output", save_videoshot_name="快照")
        :param save_videoshot_path: 视频快照保存路径。
        :param save_videoshot_name: 视频快照保存名称。保存的名字是f"{save_videoshot_path}{save_videoshot_name}_{i}.jpg"
        :param index: 是否需要视频快照的索引。默认为0表示不需要。
        :return: (list)视频快照地址
        """
        self.videoshot_url = "https://api.bilibili.com/x/player/videoshot"
        params = {
            "bvid": self.bv,
            "index": index
        }
        r = requests.get(url=self.videoshot_url, headers=self.headers, params=params)
        r_json = r.json()
        # print(r_json)
        videoshot_url = r_json["data"]["image"]
        for i, url in enumerate(videoshot_url):
            url = "https:" + url
            videoshot_content = requests.get(url=url, headers=self.headers).content
            self._save_pic(videoshot_content, save_videoshot_path, save_videoshot_name+'_'+str(i))
        return videoshot_url

    def to_csv(self):
        """
        将视频信息转为DataFrame
        [使用方法]:
            bvs_popular_df = pd.read_excel("input/xlsx_data/bvs_popular.xlsx")  # 读取bv号数据
            bvs_popular = bvs_popular_df[0].tolist()
            print(len(bvs_popular))
            bv_content_df = pd.read_excel("input/xlsx_data/bvs_popular_msg.xlsx")

            for i, bvs in enumerate(bvs_popular):
                # 第352个视频BV1H1421R7i8的信息获取失败，因为tmd是星铁生日会
                print(f"正在获取第{i+1}个视频信息: {bvs}")
                biliV = biliVideo(bvs)
                biliV.get_html()
                biliV.get_content()
                bv_content_df = pd.concat([bv_content_df, biliV.to_csv()], axis=0)
                time.sleep(random.uniform(1, 2))
                if i % 5 == 0:
                    # 每5个视频保存一次，防止寄了
                    bv_content_df.to_excel("input/xlsx_data/bvs_popular_msg.xlsx", index=False)

            bv_content_df.to_excel("input/xlsx_data/bvs_popular_msg.xlsx", index=False)
        :return:
        """
        data = {
            "av": [self.av],
            "bv": [self.bv],
            "title": [self.title],
            "pic": [self.pic],
            "desc": [self.desc],
            "view": [self.view],
            "dm": [self.dm],
            "reply": [self.reply],
            "time": [self.time],
            "like": [self.like],
            "coin": [self.coin],
            "fav": [self.fav],
            "share": [self.share],
        }
        df = pd.DataFrame(data)
        return df

    def show_values(self):
        print(CT('av号: ').blue() + f"{self.av}")
        print(CT('bv号: ').blue() + f"{self.bv}")
        print(CT('标题: ').blue() + f"{self.title}")
        print(CT('图片地址: ').blue() + f"{self.pic}")
        print(CT('简介: ').blue() + f"{self.desc}")
        print(CT('播放量: ').blue() + f"{self.view}")
        print(CT('弹幕数: ').blue() + f"{self.dm}")
        print(CT('评论数: ').blue() + f"{self.reply}")
        print(CT('发布时间: ').blue() + f"{self.time}")
        print(CT('点赞数: ').blue() + f"{self.like}")
        print(CT('硬币数: ').blue() + f"{self.coin}")
        print(CT('收藏数: ').blue() + f"{self.fav}")
        print(CT('分享数: ').blue() + f"{self.share}")


# b站评论相关操作(目前已实现发布评论功能， todo: 爬取评论)
class biliReply:
    """暂时只支持视频评论"""
    def __init__(self, bv=None, av=None):
        """
        :param bv: bv号(bv号和av号有且只能有一个不为None)
        :param av: av号(bv号和av号有且只能有一个不为None)
        """
        self.bv = bv
        self.headers = {
            "User-Agent": useragent().pcChrome,
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
            biliLogin(self.headers).get_login_state()
        else:
            print("评论成功")
            print("评论rpid：", reply_data["data"]["rpid"])
            print("评论内容：", reply_data["data"]["reply"]["content"]["message"])


# b站私信功能
class biliMessage:
    def __init__(self):
        self.headers = {
            "User-Agent": useragent().pcChrome,
            "Cookie": cookies().bilicookie,
            'referer': 'https://message.bilibili.com/'
        }

    def send_msg(self, sender_uid, receiver_id, content, msg_type=1):
        """
        发送私信
        [使用方法]
            biliM = biliMessage()
            biliM.send_msg(506925078, 381978872, "你好，请问是千年的爱丽丝同学吗？")
        :param sender_uid: 发送者mid
        :param receiver_id: 接收者mid
        :param content: 内容
        :param msg_type: 消息类型。1:发送文字 2:发送图片 5:撤回消息
        :return:
        """
        url = 'https://api.vc.bilibili.com/web_im/v1/web_im/send_msg'
        # 设备id(这个参数我大号是B182F410-3865-46ED-840F-B58B71A78B5E，小号是281ED237-9433-4BF5-BECC-D00AC88E69BF，
        # 但是换过来也能用，估计这个参数不严格)
        dev_id = AuthUtil.get_dev_id()
        timestamp = AuthUtil.get_timestamp()  # 时间戳（秒）
        data = {
            'msg[sender_uid]': sender_uid,
            'msg[receiver_id]': receiver_id,
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
            'csrf': cookies().bili_jct
        }
        r = requests.post(url, data=data, headers=self.headers)
        r_json = r.json()
        if r_json['code'] == 0:
            msg_content = r_json['data']['msg_content']
            content_dict = json.loads(msg_content)
            content_value = content_dict['content']
            print("发送成功，内容是：", content_value)
        else:
            print("发送失败，错误码：", r_json['code'])


# b站收藏夹功能
class biliFav:
    def __init__(self):
        self.mid = None
        self.headers = None
        self.fav_ids_url = "https://api.bilibili.com/x/v3/fav/resource/ids"
        self.init_params()

    def get_fav_bv(self, media_id):
        fav_bvids = None
        params = {"media_id": media_id}
        r = requests.get(url=self.fav_ids_url, headers=self.headers, params=params)
        fav_data = r.json()
        if fav_data["code"] != 0:
            print(f"获取收藏夹{media_id}失败，错误码{fav_data['code']}")
        else:
            fav_list = fav_data["data"]
            fav_bvids = [fav["bvid"] for fav in fav_list]
        return fav_bvids

    def init_params(self):
        headers = {
            "User-Agent": useragent().pcChrome,
            "Cookie": cookies().bilicookie,
            'referer': 'https://www.bilibili.com/'
        }
        login_msg = biliLogin(headers).get_login_state()
        self.mid = login_msg["data"]["mid"]  # 用户UID
        self.headers = {
            "User-Agent": useragent().pcChrome,
            "Cookie": cookies().bilicookie,
            'referer': f'https://space.bilibili.com/{self.mid}/favlist'
        }

# 获取b站合集视频列表
class biliArchive:
    def __init__(self, cookie_path='cookie/qr_login.txt'):
        self.headers = {
            "User-Agent": useragent().pcChrome,
            "Cookie": cookies(path=cookie_path).bilicookie,
        }
        # 视频合集列表
        self.url_archives_list = "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"

        # 用户UID/mid
        login_msg = biliLogin(self.headers).get_login_state()
        self.mid = login_msg["data"]["mid"]

    def get_archives_list(self, season_id):
        """
        获取视频合集列表
        [使用方法]:
            biliA = biliArchive()
            # 和纱猫猫小剧场, url: https://space.bilibili.com/37507923/channel/collectiondetail?sid=2033914
            bvids = biliA.get_archives_list(2033914)
            print(bvids)
        :return: list, 视频BV号列表
        """
        # 请求self.url_archives_list，参数是season_id与mid
        params = {
            "season_id": season_id,
            "mid": self.mid
        }
        r = requests.get(url=self.url_archives_list, headers=self.headers, params=params)
        r_json = r.json()
        if r_json["code"] == 0:
            archives_list = r_json["data"]["archives"]
            bv_list = [archive["bvid"] for archive in archives_list]
            return bv_list
        else:
            print(f"获取视频合集列表失败，错误码：{r_json['code']}，错误信息：{r_json['message']}")
            return None


# b站的一些排行榜(目前建议只使用get_popular，其余的不太行的样子)
class biliRank:
    def __init__(self):
        self.headers = {
            "User-Agent": useragent().pcChrome,
            "Cookie": cookies().bilicookie,
        }
        self.headers_no_cookie = {
            "User-Agent": useragent().pcChrome,
        }
        self.url_popular = "https://api.bilibili.com/x/web-interface/popular"
        self.url_ranking = "https://api.bilibili.com/x/web-interface/ranking/v2"
        self.url_new = "https://api.bilibili.com/x/web-interface/dynamic/region"

    def get_popular(self, use_cookie=True, pn=1, ps=20):
        """
        获取综合热门视频列表：https://www.bilibili.com/v/popular/all
        文档：https://socialsisteryi.github.io/bilibili-API-collect/docs/video_ranking/popular.html
        [使用方法]:
            bvs = biliRank().get_popular()
        [注意]可以使用下面的方法获取热门视频列表：
            bvs = []
            for i in range(1, 6):
                bvs.extend(biliRank().get_popular(pn=i))
            print(bvs)
        :param use_cookie: 是否使用cookie
        :param pn: 页码
        :param ps: 每页项数
        :return: 视频的bv号列表
        """
        params = {
            "pn": pn,
            "ps": ps
        }
        if use_cookie:
            r = requests.get(url=self.url_popular, headers=self.headers, params=params)
        else:
            r = requests.get(url=self.url_popular, headers=self.headers_no_cookie, params=params)
        popular_data = r.json()
        # print("热门视频：")
        # for i, video in enumerate(popular_data["data"]["list"]):
        #     print(f"{i+1}.{video['bvid']} {video['title']}")
        # 将BV号用list返回
        return [video['bvid'] for video in popular_data["data"]["list"]]

    def get_ranking(self, tid=None):
        """
        获取排行榜视频列表：https://www.bilibili.com/v/popular/rank/all
        [使用方法]:
            biliRank().get_ranking()
        :param tid: [有问题]分区id，但似乎不起作用。文档: https://socialsisteryi.github.io/bilibili-API-collect/docs/video/video_zone.html
        :return: 视频的bv号列表
        """
        if tid is not None:
            r = requests.get(url=self.url_ranking, headers=self.headers, params={"tid": tid})
        else:
            r = requests.get(url=self.url_ranking, headers=self.headers)
        ranking_data = r.json()
        print("排行榜：")
        for i, video in enumerate(ranking_data["data"]["list"]):
            print(f"{i+1}.{video['bvid']} {video['title']}")
        return [video['bvid'] for video in ranking_data["data"]["list"]]

    def get_new(self, rid=1, pn=1, ps=5):
        """
        [有问题]获取新视频列表，但似乎不是最新的，目前不知道是干什么的
        [使用方法]:
            biliRank().get_new()
        :param rid: [必要]目标分区tid
        :param pn: 页码
        :param ps: 每页项数
        """
        params = {
            "rid": rid,
            "pn": pn,
            "ps": ps
        }
        r = requests.get(url=self.url_new, headers=self.headers, params=params)
        new_data = r.json()
        print("新视频：")
        for i, video in enumerate(new_data["data"]["archives"]):
            print(f"{i+1}.{video['bvid']} {video['title']}")
        return [video['bvid'] for video in new_data["data"]["archives"]]


if __name__ == '__main__':
    # biliM = biliMessage()
    # biliM.send_msg(506925078, 381978872, "催更[doge]")

    # biliV = biliVideo("BV1ov42117yC")
    # biliV.get_html()
    # biliV.get_content()
    # biliV.download_pic(save_pic_path="output", save_pic_name="BV1ov42117yC封面")

    # biliL = biliLogin()
    # biliL.qr_login()
    # headers = {
    #     "User-Agent": useragent().pcChrome,
    #     "Cookie": cookies(path='cookie/qr_login.txt').bilicookie,
    #     'referer': "https://www.bilibili.com"
    # }
    # biliLogin(headers).get_login_state()
    # biliR = biliReply(bv="BV1ov42117yC")
    # biliR.send_reply("可爱的白州梓！[喜欢]")

    # biliR = biliReply(bv="BV1Ss421M7VJ")
    # biliR.send_reply("兄弟你好香啊😋")

    # biliF = biliFav()
    # bvids = biliF.get_fav_bv(2525700378)
    # print(bvids)
    biliA = biliArchive()
    bvids = biliA.get_archives_list(2033914)
    print(bvids)
    # biliM = biliMessage()
    # biliM.send_msg(3493133776062465, 506925078, "你好，请问是千年的爱丽丝同学吗？")
    pass



