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

from src.util.Colorful_Console import ColoredText as CT  # 用于控制台的彩色输出
from src.bili_util import BV2AV  # BV号和AV号的转换
from src.bili_util import AuthUtil  # 获取鉴权参数
from src.bili_util import BiliVideoUtil  # B站视频工具
from src.config import UserAgent  # User-Agent
from src.config import bilicookies as cookies  # B站cookie
from src.config import Config  # 加载配置信息

config = Config()


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

    def qr_login(self, save_path="cookie", save_name="qr_login", full_path=None, img_show=True):
        """
        扫码登录
        [Warning]:
            请妥善保管cookie的路径，本方法只会保存一份cookie到本地的指定路径里
        [使用方法-扫码登录，指定自定义保存cookie的路径，然后检查登录状态]:
            full_path = 'cookie/cookie_大号.txt'  # 这里只是为了展示更改路径，实际使用时仍然建议使用默认路径cookie/qr_login.txt
            biliL = biliLogin()
            biliL.qr_login(full_path=full_path)  # 扫码登录
            headers = {
                "User-Agent": useragent().pcChrome,
                "Cookie": cookies(path=full_path).bilicookie,
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
        :param save_path: 保存二维码、cookie的路径
        :param save_name: 保存二维码、cookie的文件名
        :param full_path: cookie的全路径名称(含路径、文件名、后缀)，指定此参数时，其余与cookie路径相关的信息均失效
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
                self._save_cookie(get_cookie, save_path, save_name, full_path)
                return True
            else:
                print('[biliLogin-qr_login]未知错误')
            elapsed_time = time.time() - start_time
            if elapsed_time > 60:
                print('[biliLogin-qr_login]超过一分钟，返回False')
                return False
            time.sleep(1)

    def _save_cookie(self, cookie, save_path=None, save_name=None, full_path=None):
        """
        保存cookie
        :param cookie: 原始cookie
        :param save_path: 保存路径
        :param save_name: 保存文件名
        :param full_path: 全路径名称(含路径、文件名、后缀)，指定此参数时，其余与路径相关的信息均失效
        """
        if full_path is not None:
            # 检查路径是否存在，不存在则创建
            if not os.path.exists(os.path.dirname(full_path)):
                os.makedirs(os.path.dirname(full_path))
            file_path = full_path
        else:
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
            print(f"[biliLogin-_save_cookie]cookie已保存在{file_path}")
            file.write(cookie)


# 获取b站视频信息(目前已实现获取视频信息，下载视频、音频、封面、快照功能)
# 对于不确定的视频，请务必先检查其属性值accessible是否为True，在biliVideo各个板块中不一定主动判断了该值。
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
            title: 标题
            pic: 封面路径
            desc: 简介
            stat: 统计数据，比如{'aid': 1003283555, 'view': 27847, 'danmaku': 76, 'reply': 143, 'favorite': 1458,
                                'coin': 201, 'share': 40, 'now_rank': 0, 'his_rank': 0, 'like': 1566, 'dislike': 0,
                                'evaluation': '', 'vt': 0, 'viewseo': 27847}
            view: 播放量
            dm: 弹幕量
            reply: 评论量
            time: 稿件发布时间pubdate，相对应的是ctime(用户投稿时间)，这里不给出ctime
            like: 点赞量
            coin: 投币量
            fav: 收藏量
            share: 转发量
            tag: 标签(注意视频底下的标签里除了tag还有其他的，应该是分区)
            tid: 分区tid，可参考https://socialsisteryi.github.io/bilibili-API-collect/docs/video/video_zone.html
            tname: 子分区名称(疑似BAC注释不够清晰，其实tid与tname是一样的，都是子分区)
          额外信息：
            down_video_json: 视频的下载信息（包含视频与音频地址，在download_video()与download_audio()中获取）
          外部存储：
            cookie_path: 本地cookie路径

        :param bv: bv号
        :param av: av号
        :param cookie_path: 本地cookie路径。默认为 LOGIN_COOKIE_PATH = "cookie/qr_login.txt"

        """
        # 初始化信息
        super().__init__(bv=bv, av=av)
        if cookie_path is None:
            cookie_path = config.LOGIN_COOKIE_PATH
            # warning_text = "[此警告可忽略] cookie_path参数未指定，默认为 'cookie/qr_login.txt' ，请注意是否是所需要的cookie。"
            # modify_tip = '请修改为类似这样的参数传递：cookie_path="cookie/qr_login.txt"'
            # warnings.warn(warning_text + "[Tips]: " + modify_tip, stacklevel=1)

        self.url_bv = f"https://www.bilibili.com/video/{self.bv}"  # 视频链接
        self.url_stat = f"https://api.bilibili.com/x/web-interface/view?bvid={self.bv}"  # 视频信息
        self.url_stat_detail = f"https://api.bilibili.com/x/web-interface/view/detail?bvid={self.bv}"  # 视频详细信息
        self.url_tag = "https://api.bilibili.com/x/tag/archive/tags"  # 视频标签
        self.url_play = "https://api.bilibili.com/x/player/wbi/playurl"  # 视频下载
        self.url_up = "https://api.bilibili.com/x/web-interface/card"  # up主信息(简略)

        self.headers = {
            "User-Agent": UserAgent().pcChrome,
            "Cookie": cookies(path=cookie_path).bilicookie,
            'referer': self.url_bv
        }

        # # 网页文本
        # self.rtext = None  # 网页的文本，也就是r.text(因为后面基本使用api，所以这个属性已经废弃)

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
        # 视频tag与分区
        self.tag = None  # 视频的标签
        self.tid = None  # 视频的分区tid
        self.tname = None  # 视频的子分区名称
        # 视频作者
        self.up = None  # 视频的up主昵称
        self.up_mid = None  # 视频的up主的mid
        self.up_follow = None  # 视频的up主是否关注 0,1
        self.up_followers = None  # 视频的up主的粉丝数

        # 额外信息
        self.down_video_json = None  # 视频的下载信息

        # 用户信息
        self.user_like = None  # 用户是否点赞 0,1
        self.user_coin = None  # 用户投币数量 0,1,2
        self.user_fav = None  # 用户是否收藏 0,1

        # 自动调用的方法
        # self.get_html()  # 自动获取html(因为后面基本使用api，所以这个方法已经废弃)

    # [×]这个方法已经废弃，因为后面基本使用api。用于获取html
    def get_html(self):
        """
        获取html
        [使用方法]:
            biliV = biliVideo("BV1ov42117yC")
            biliV.get_html()
        :return:
        """
        # biliLogin(self.headers).get_login_state()  # 为了防止检查次数过多，这里注释掉了，需要时可以取消注释
        r = requests.get(url=self.url_bv, headers=self.headers)
        r.encoding = 'utf-8'
        self.rtext = r.text
        # if self.html_path is not None:
        #     if not os.path.exists(self.html_path):
        #         os.makedirs(self.html_path)
        #     with open(f"{self.html_path}{self.bv}.html", 'w', encoding='utf-8') as f:
        #         f.write(self.rtext)

    # 用于获取视频信息
    def get_content(self, stat=True, tag=True, up=True):
        """
        [使用方法]:
            biliV = biliVideo("BV18x4y187DE")
            biliV.get_html()  # [必要]获取html
            biliV.get_content()
        文档：https://socialsisteryi.github.io/bilibili-API-collect/docs/video/info.html
        """
        # 获取视频信息
        if stat:
            r = requests.get(url=self.url_stat, headers=self.headers)
            r_json = r.json()
            # 获取视频信息错误
            if r_json["code"] != 0:
                print(f"获取视频信息失败，错误代码：{r_json['code']}，错误信息：{r_json['message']}")
                return False
            # 检查aid是否一致
            aid = r_json["data"]["aid"]
            if self.av != aid:
                error_text = f'av:{self.av}，bv:{self.bv}有误。'
                modify_tip = f'请检查{self.av}与爬取到的av:{aid}，是否一致。另外传入的bv是{self.bv}'
                raise ValueError(error_text + "[Tips:]" + modify_tip)
            # 开始真正获取信息
            self.title = r_json["data"]["title"]
            self.pic = r_json["data"]["pic"]
            self.desc = r_json["data"]["desc"]
            self.stat = r_json["data"]["stat"]
            self.view = self.stat["view"]
            self.dm = self.stat["danmaku"]
            self.reply = self.stat["reply"]
            self.time = r_json["data"]["pubdate"]
            self.like = self.stat["like"]
            self.coin = self.stat["coin"]
            self.fav = self.stat["favorite"]
            self.share = self.stat["share"]
            self.tid = r_json["data"]["tid"]
            self.tname = r_json["data"]["tname"]
            self.up = r_json["data"]["owner"]["name"]
            self.up_mid = r_json["data"]["owner"]["mid"]

        # 获取up主信息(除了name与mid之外的：是否关注up、up粉丝数)
        if up:
            r = requests.get(url=self.url_up, headers=self.headers, params={"mid": self.up_mid})
            r_json = r.json()
            if r_json["code"] != 0:
                print(f"[url_up]获取up主信息失败，错误代码：{r_json['code']}，错误信息：{r_json['message']}")
                r = requests.get(url=self.url_stat_detail, headers=self.headers)
                print(f"[url_up]失效链接：{r.url}")
                r_json = r.json()
                if r_json["code"] != 0:
                    print(f"[url_bv_detail]获取up主信息失败，错误代码：{r_json['code']}，错误信息：{r_json['message']}")
                    return False
                r_data = r_json["data"]["Card"]
            else:
                r_data = r_json["data"]
            self.up_follow = 1 if r_data["following"] else 0
            self.up_followers = r_data["follower"]

        # 获取视频标签
        if tag:
            r = requests.get(url=self.url_tag, headers=self.headers, params={"bvid": self.bv})
            r_json = r.json()
            if r_json["code"] != 0:
                print(f"获取标签信息失败，错误代码：{r_json['code']}，错误信息：{r_json['message']}")
                return False
            r_json = r_json["data"]
            self.tag = [tag["tag_name"] for tag in r_json]

    # 下载视频
    def download_video(self, save_video_path=None, save_video_name=None, save_video_add_desc="视频(无音频)",
                       full_path=None, qn=80, platform="pc", high_quality=1, fnval=16):
        """
        [使用方法]:
            biliV = biliVideo("BV18x4y187DE")
            biliV.download_video()
        参数具体请查看 `BAC文档
        <https://socialsisteryi.github.io/bilibili-API-collect/docs/video/videostream_url.html>`_.
        :param save_video_path: 视频保存路径。路径为f"{save_video_path}{self.bv}.mp4"。如不指定，则保存在当前目录下f"{self.bv}.mp4"
        :param save_video_name: 视频保存名称。
        :param save_video_add_desc: 视频保存名称的附加描述
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
            video_content = requests.get(url=self.down_video_json["data"]["durl"][0]["url"],
                                         headers=self.headers).content
        else:
            video_content = requests.get(url=self.down_video_json["data"]["dash"]["video"][0]["baseUrl"],
                                         headers=self.headers).content
        self._save_mp4(video_content, save_video_path, save_video_name, add_desc=save_video_add_desc,
                       full_path=full_path)
        return True

    # 下载音频
    def download_audio(self, save_audio_path=None, save_audio_name=None, save_audio_add_desc="音频",
                       full_path=None, fnval=16):
        """
        下载音频。如果视频音频都要，建议在download_video之后使用，这样能减少一次请求。
        [使用方法]:
            biliV = biliVideo("BV12a411k7os")
            biliV.download_audio(save_audio_path="output")
        :param save_audio_path: 音频保存路径
        :param save_audio_name: 音频保存名称
        :param save_audio_add_desc: 音频保存名称的附加描述
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
        self._save_mp3(audio_content, save_audio_path, save_audio_name, add_desc=save_audio_add_desc,
                       full_path=full_path)
        return True

    # 下载视频与音频，然后使用ffmpeg或moviepy合并(优先使用ffmpeg)
    def download_video_with_audio(self, auto_remove=True,
                                  save_video_path=None, save_video_name=None, save_video_add_desc="视频(无音频)",
                                  save_audio_path=None, save_audio_name=None, save_audio_add_desc="音频",
                                  save_path=None, save_name=None, save_add_desc="视频"):
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
        :param save_video_add_desc: 视频保存名称的附加描述
        :param save_audio_path: 音频保存路径
        :param save_audio_name: 音频保存名称
        :param save_audio_add_desc: 音频保存名称的附加描述
        :param save_path: 合并后的视频保存路径
        :param save_name: 合并后的视频保存名称
        :param save_add_desc: 合并后的视频保存名称的附加描述
        """
        self.check_path([save_video_path, save_audio_path, save_path])
        video_path = self._get_path(save_video_path, save_video_name, add_desc=save_video_add_desc, save_type="mp4")
        audio_path = self._get_path(save_audio_path, save_audio_name, add_desc=save_audio_add_desc, save_type="mp3")
        va_path = self._get_path(save_path, save_name, add_desc=save_add_desc, save_type="mp4")
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

    # 下载封面
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

    # 下载快照
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
            self._save_pic(videoshot_content, save_videoshot_path, save_videoshot_name + '_' + str(i))
        return videoshot_url

    # 获取观众是否点赞、投币、收藏该视频
    def get_user_action(self):
        """
        获取观众是否点赞、投币、收藏该视频
        事实上，因为B站点赞过一段时间后会自动取消，所以点赞的信息可能不准确。
        可以尝试点赞，看看状态码是不是65006重复点赞（不过因为点赞视频这个功能还没实现，现在先咕咕咕）：
        点赞视频url：https://api.bilibili.com/x/web-interface/archive/like
        文档：https://socialsisteryi.github.io/bilibili-API-collect/docs/video/action.html
        [使用方法]:
            full_path = 'cookie/cookie_大号.txt'
            biliV = biliVideo("BV1ov42117yC", cookie_path=full_path)
            s = biliV.get_user_action()
            if s:
                print(biliV.user_like, biliV.user_coin, biliV.user_fav)
            else:
                print("获取失败")
        :return: 观众是否点赞、投币、收藏该视频
        """
        url_like = "https://api.bilibili.com/x/web-interface/archive/has/like"
        url_coin = "https://api.bilibili.com/x/web-interface/archive/coins"
        url_fav = "https://api.bilibili.com/x/v2/fav/video/favoured"
        params = {
            "aid": self.av
        }
        r_like = requests.get(url=url_like, headers=self.headers, params=params)
        r_coin = requests.get(url=url_coin, headers=self.headers, params=params)
        r_fav = requests.get(url=url_fav, headers=self.headers, params=params)
        like_json = r_like.json()
        coin_json = r_coin.json()
        fav_json = r_fav.json()
        if like_json["code"] != 0:
            print(f"获取点赞信息失败，错误代码：{like_json['code']}，错误信息：{like_json['message']}")
            return False
        if coin_json["code"] != 0:
            print(f"获取投币信息失败，错误代码：{coin_json['code']}，错误信息：{coin_json['message']}")
            return False
        if fav_json["code"] != 0:
            print(f"获取收藏信息失败，错误代码：{fav_json['code']}，错误信息：{fav_json['message']}")
            return False
        self.user_like = like_json["data"]  # 0：未点赞, 1：已点赞
        self.user_coin = coin_json["data"]["multiply"]  # 投币个数
        self.user_fav = 1 if fav_json["data"]["favoured"] else 0  # true：未收藏, false：已收藏 -> 0：未收藏, 1：已收藏
        return True

    # 将视频信息转为DataFrame(暂时没有写得很好，后续会优化)
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

    # 显示视频信息
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
        print(CT('标签: ').blue() + f"{self.tag}")
        print(CT('分区tid: ').blue() + f"{self.tid}")
        print(CT('子分区名称: ').blue() + f"{self.tname}")
        print(CT('up主: ').blue() + f"{self.up}")
        print(CT('up主mid: ').blue() + f"{self.up_mid}")
        print(CT('是否关注up主: ').blue() + f"{self.up_follow}")
        print(CT('up主粉丝数: ').blue() + f"{self.up_followers}")
        print(CT('是否点赞: ').blue() + f"{self.user_like}")
        print(CT('投币数量: ').blue() + f"{self.user_coin}")
        print(CT('是否收藏: ').blue() + f"{self.user_fav}")


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


# b站私信(目前已实现发送私信功能)
class biliMessage:
    def __init__(self):
        self.headers = {
            "User-Agent": UserAgent().pcChrome,
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


# b站收藏夹(目前已实现获取收藏夹视频功能)
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
            "User-Agent": UserAgent().pcChrome,
            "Cookie": cookies().bilicookie,
            'referer': 'https://www.bilibili.com/'
        }
        login_msg = BiliLogin(headers).get_login_state()
        self.mid = login_msg["data"]["mid"]  # 用户UID
        self.headers = {
            "User-Agent": UserAgent().pcChrome,
            "Cookie": cookies().bilicookie,
            'referer': f'https://space.bilibili.com/{self.mid}/favlist'
        }


# b站合集视频(目前已实现获取视频合集列表功能)
class biliArchive:
    def __init__(self, cookie_path='cookie/qr_login.txt'):
        self.headers = {
            "User-Agent": UserAgent().pcChrome,
            "Cookie": cookies(path=cookie_path).bilicookie,
        }
        # 视频合集列表
        self.url_archives_list = "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"

        # 用户UID/mid
        login_msg = BiliLogin(self.headers).get_login_state()
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


# b站历史记录
class biliHistory:
    def __init__(self, cookie_path='cookie/qr_login.txt'):
        self.cookie_path = cookie_path
        self.headers = {
            "User-Agent": UserAgent().pcChrome,
            "Cookie": cookies(path=cookie_path).bilicookie,
            'referer': 'https://www.bilibili.com/'
        }
        self.url_history = "https://api.bilibili.com/x/web-interface/history/cursor"  # 历史记录url
        self.last_cursor = None  # 上一页的cursor

        self.oid_list = []  # oid列表，是
        self.archive_list = []  # 视频BV号列表
        self.bv_process_list = []  # (对应archive_list)观看进度列表
        self.bv_duration_list = []  # (对应archive_list)视频时长列表
        self.view_at_list = []  # (对应archive_list)观看时间列表
        self.pgc_list = []  # 剧集(番剧/影视)ssid列表
        self.live_list = []  # 直播间id列表
        self.articlelist_list = []  # 文集rlid列表
        self.article_list = []  # 文章cvid列表

    # 获取历史记录(不建议调用这个函数，这个函数是获取单页记录)
    def get_history(self, max_id=0, business="", view_at=0, filter_type="all", ps=20):
        """
        获取历史记录
        [使用方法-获取单页记录]:
            full_path = 'cookie/cookie_大号.txt'  # 这里只是为了展示更改路径，实际使用时仍然建议使用默认路径cookie/qr_login.txt
            biliH = biliHistory(cookie_path=full_path)
            success = biliH.get_history()
            if success:
                print(f"oid列表， {len(biliH.oid_list)}个：{biliH.oid_list}")
                print(f"视频BV号列表, {len(biliH.archive_list)}个：{biliH.archive_list}")
                print(f"剧集(番剧/影视)ssid列表, {len(biliH.pgc_list)}个：{biliH.pgc_list}")
                print(f"直播间id列表, {len(biliH.live_list)}个：{biliH.live_list}")
                print(f"文集rlid列表, {len(biliH.articlelist_list)}个：{biliH.articlelist_list}")
                print(f"文章cvid列表, {len(biliH.archive_list)}个：{biliH.article_list}")
                print(f"上一页的cursor：{biliH.last_cursor}")
        :param max_id: 历史记录截止目标 id。稿件avid，剧集(番剧/影视)ssid，直播间id，文集rlid，文章cvid
        :param business: 历史记录截止目标业务类型。archive稿件，pgc剧集(番剧/影视), live直播, article-list文集, article文章
        :param view_at: 历史记录截止时间。默认为 0，为当前时间
        :param filter_type: 历史记录分类筛选。archive稿件，live直播，article文章
        :param ps: 每页项数。默认为 20，最大 30
        :return: list, 视频BV号列表
        """
        params = {
            "max": max_id,
            "business": business,
            "view_at": view_at,
            "type": filter_type,
            "ps": ps
        }
        r = requests.get(url=self.url_history, headers=self.headers, params=params)
        r_json = r.json()
        if r_json["code"] == 0:
            history_list = r_json["data"]["list"]
            for history in history_list:
                stat = history["history"]  # 条目详细信息
                stat_business = stat["business"]  # 业务类型
                self.oid_list.append(stat["oid"])
                if stat_business == "archive":
                    self.archive_list.append(stat["bvid"])  # 视频
                    self.bv_process_list.append(history["progress"])  # 视频观看进度
                    self.bv_duration_list.append(history["duration"])  # 视频时长
                    self.view_at_list.append(history["view_at"])  # 观看时间戳
                elif stat_business == "pgc":
                    self.pgc_list.append(stat["epid"])  # 剧集(番剧/影视)
                elif stat_business == "live":
                    self.live_list.append(stat["oid"])  # 直播间
                elif stat_business == "article-list":
                    self.articlelist_list.append(stat["oid"])  # 文集
                elif stat_business == "article":
                    self.article_list.append(stat["oid"])  # 文章
                else:
                    print(f"未知的历史记录类型：{history['history']['business']}")
            self.last_cursor = r_json["data"]["cursor"]
            return True
        elif r_json["code"] == -101:
            print("获取历史记录失败，错误码：-101，错误信息：账号未登录")
            return None
        else:
            print(f"获取历史记录失败，错误码：{r_json['code']}，错误信息：{r_json['message']}")
            return None

    # 获取所有历史记录(建议使用这个函数，但是需要自己指定合适的max_iter，获取到的历史记录总数为max_iter*ps)
    def get_history_all(self, max_iter=5, filter_type="all", ps=20, **kwargs):
        """
        获取所有历史记录
        [使用方法-获取所有记录]:
        """
        max_id = kwargs.get("max_id", 0)
        business = kwargs.get("business", "")
        view_at = kwargs.get("view_at", 0)
        for i in range(max_iter):
            print(f"\r正在获取第{i + 1}/{max_iter}页历史记录", end='')
            success = self.get_history(max_id=max_id, business=business, view_at=view_at, filter_type=filter_type,
                                       ps=ps)
            if success:
                max_id = self.last_cursor["max"]
                business = self.last_cursor["business"]
                view_at = self.last_cursor["view_at"]
            else:
                print("获取历史记录失败")
                return False
            time.sleep(random.uniform(0.2, 0.5))
        last_cursor = f"最后一次的 max_id='{max_id}', business='{business}', view_at='{view_at}'"
        print(f"\n{last_cursor}")
        # 将last_cursor写入文件output/temp_last_cursor.txt，以便下次继续获取
        # 检查路径是否存在
        if not os.path.exists("output"):
            os.makedirs("output")
        with open("output/temp_last_cursor.txt", "w", encoding="utf-8") as f:
            f.write(last_cursor)
        return True

    # 打印获取到的历史记录
    def log_history(self):
        print("\n获取到的历史记录如下：")
        print(f"oid列表， {len(self.oid_list)}个：{self.oid_list}")
        print(f"视频BV号列表, {len(self.archive_list)}个：{self.archive_list}")
        print(f"剧集(番剧/影视)ssid列表, {len(self.pgc_list)}个：{self.pgc_list}")
        print(f"直播间id列表, {len(self.live_list)}个：{self.live_list}")
        print(f"文集rlid列表, {len(self.articlelist_list)}个：{self.articlelist_list}")
        print(f"文章cvid列表, {len(self.article_list)}个：{self.article_list}")
        print(f"上一页的cursor：{self.last_cursor}")

    # 保存历史记录。因为视频是最主要的，所以这里给出的是保存历史记录中的视频信息
    def save_video_history_df(self, view_info=True, detailed_info=False,
                              save_path="output", save_name="history", add_df=True):
        """
        保存历史记录中的视频信息，有bv号、观看进度
        :param view_info: 是否需要保存观看信息：你是否对视频点赞、投币、收藏了。(分享功能暂时没办法)
        :param detailed_info: 是否需要额外保存详细信息：视频的各种stat，具体请见下面的代码或者是biliVideo中实现的属性。
        :param save_path: xlsx的保存路径
        :param save_name: xlsx的保存名称
        :param add_df: 当文件存在时，是否使用追加数据而不是覆盖数据。默认为True(追加), 反之是False(覆盖)
        :return: df
        """
        # 检查路径是否存在
        if not os.path.exists(save_path):
            os.makedirs(save_path)

        view_percent_list = [
            "100.00%" if p == -1 else
            "-1.00%" if d == 0 else
            f"{round(p / d * 100, 2):.2f}%"
            for p, d in zip(self.bv_process_list, self.bv_duration_list)
        ]
        data = {
            "bv": self.archive_list,
            "progress": self.bv_process_list,
            "duration": self.bv_duration_list,
            "view_percent": view_percent_list,
            "view_time": self.view_at_list
        }
        if view_info:
            data["u_like"] = []
            data["u_coin"] = []
            data["u_fav"] = []
            data["u_score"] = []  # 该值是u_like+u_coin+u_fav*2。比如点赞了+投1币+没收藏=2，点赞+没投币+收藏=3
        if detailed_info:
            data["title"] = []
            data["view"] = []
            data["dm"] = []
            data["reply"] = []
            data["time"] = []
            data["like"] = []
            data["coin"] = []
            data["fav"] = []
            data["share"] = []
            data["tag"] = []
            data["tid"] = []
            data["up_name"] = []
            data["up_follow"] = []
            data["up_followers"] = []
        # 获取视频信息
        total_videos = len(self.archive_list)
        for i, bv in enumerate(self.archive_list):
            print(f"\r正在获取第 {i + 1}/{total_videos} 个视频 {bv} 的观看信息", end='')
            biliV = biliVideo(bv, cookie_path=self.cookie_path)
            if view_info:
                biliV.get_user_action()
                data["u_like"].append(biliV.user_like)
                data["u_coin"].append(biliV.user_coin)
                data["u_fav"].append(biliV.user_fav)
                data["u_score"].append(biliV.user_like + biliV.user_coin + biliV.user_fav * 2)
                # print(f"点赞：{biliV.user_like}，投币：{biliV.user_coin}，收藏：{biliV.user_fav}")
            if detailed_info:
                biliV.get_content()
                data["title"].append(biliV.title)
                data["view"].append(biliV.view)
                data["dm"].append(biliV.dm)
                data["reply"].append(biliV.reply)
                data["time"].append(biliV.time)
                data["like"].append(biliV.like)
                data["coin"].append(biliV.coin)
                data["fav"].append(biliV.fav)
                data["share"].append(biliV.share)
                data["tag"].append(biliV.tag)
                data["tid"].append(biliV.tid)
                data["up_name"].append(biliV.up)
                data["up_follow"].append(biliV.up_follow)
                data["up_followers"].append(biliV.up_followers)
            time.sleep(random.uniform(0.3, 0.5))
            # 如果i能被25整除，就保存一次，防止数据丢失
            if i % 25 == 0:
                # 选择前i+1个数据保存一次
                temp_data = {k: v[:i + 1] for k, v in data.items()}
                temp_df = pd.DataFrame(temp_data)
                temp_df.to_excel(f"{save_path}/temp_{save_name}.xlsx", index=False)
                print(f"\n[save_video_history_df]已临时保存{i + 1}个视频的观看信息到{save_path}/temp_{save_name}.xlsx")
                time.sleep(random.uniform(2, 3))

        df = pd.DataFrame(data)
        file_path = f"{save_path}/{save_name}.xlsx"
        if os.path.exists(file_path) and add_df:
            print(f"\n[save_video_history_df]因为文件{file_path}已存在，正在追加数据")
            df_old = pd.read_excel(file_path)
            # 合并
            df = pd.concat([df_old, df], axis=0)
            # 按bv去重，保留view更高的
            df = df.sort_values(by='view', ascending=False)
            # 如果有重复的，就print("有重复")
            duplicates = df.duplicated(subset=['bv'], keep='first')
            if duplicates.any():
                print("有重复的bv，保留view更高的行：(出现此行代表可以结束历史记录的获取了)")
                print(df[duplicates])  # 打印重复的行
            df = df.drop_duplicates(subset=['bv'], keep='first')  # 删除bv列中重复的行，保留view更高的行，subset是指定列，keep是保留方式
            # 按view_time降序排序
            df = df.sort_values(by='view_time', ascending=False)
        df.to_excel(file_path, index=False)
        print(f"[save_video_history_df]历史记录已保存到{file_path}")
        return df

    # 通过历史记录获取已经观看但是失效了视频的信息
    def get_invalid_video(self, bv, max_iter=10, ps=20, **kwargs):
        """
        [灵感来源]:
            在使用get_history_all的时候，因为发现视频
              BV1sS411w7Fk(卡拉彼丘香奈美泳装皮靶场实机演示)，
              BV1aM4m127Ab(炎热的夏天，柴郡当然要去玩水啦～)，
            已经失效，无法通过之前的正常途径获取，但是历史记录里其实保存了的。
            所以遍历历史记录去找到这些失效视频即可。
        [使用方法]:
            full_path = 'cookie/cookie_大号.txt'  # 这里是用大号的cookie来获取大号的历史记录
            biliH = biliHistory(cookie_path=full_path)
            ans = biliH.get_invalid_video("BV1aM4m127Ab", max_iter=10)
            # 也可以定义一个列表，类似于bv_list = ["BV1Bw4m1e7JR", "BV1j1g7eaE16", "BV1Vn4y1R7fH"]，
            # 然后使用ans = biliH.get_invalid_video(bv_list, max_iter=100)也是可以的
            print(ans)
        [注意]:
            获取到的视频信息会保存在output/temp_失效视频.json中，这样使用vscode能很方便查看了
        :param bv: 视频BV号，可以是单个(str)，也可以是bv号列表(list)
        :param max_iter: 最大迭代次数，超过这个次数即使未找到也停止，(如果指定为-1，则一直查找，该功能暂未实现)
        :param ps: 每页项数
        :return: 视频信息
        """
        max_id = kwargs.get("max_id", 0)
        business = kwargs.get("business", "")
        view_at = kwargs.get("view_at", 0)
        if max_iter <= 0:
            raise ValueError("max_iter不能小于或等于0")
        elif max_iter > 100:
            warnings.warn("max_iter大于100，可能会导致请求次数过多，建议调小", UserWarning)

        if not os.path.exists("output"):
            os.makedirs("output")
        if not isinstance(bv, list):
            bv = [bv]
        bv_count = len(bv)
        found_videos = []
        video_stat = []
        for i in range(max_iter):
            print(f"\r正在获取第{i + 1}/{max_iter}页历史记录", end='')
            params = {
                "max": max_id,
                "business": business,
                "view_at": view_at,
                "type": "archive",
                "ps": ps
            }
            r = requests.get(url=self.url_history, headers=self.headers, params=params)
            r_json = r.json()
            if r_json["code"] == 0:
                history_list = r_json["data"]["list"]
                for history in history_list:
                    stat = history["history"]
                    stat_business = stat["business"]
                    if stat_business != "archive":
                        print(f"非视频的历史记录类型：{history['history']['business']}")
                        continue
                    if stat["bvid"] in bv:
                        bv.remove(stat['bvid'])  # 从列表中移除找到的 bvid
                        print(f"已找到视频{stat['bvid']}的历史记录，还剩{len(bv)}个未找到的视频")
                        found_videos.append(stat['bvid'])
                        video_stat.append(history)
                    if not bv:
                        # 如果列表中的所有视频都找到了，就提前结束
                        print(f"\n所有视频已找到")
                        print(f"找到的视频有{len(found_videos)}/{bv_count}个: {found_videos}")
                        with open("output/temp_失效视频.json", "w", encoding="utf-8") as f:
                            json.dump(video_stat, f, ensure_ascii=False, indent=4)
                        return video_stat
                self.last_cursor = r_json["data"]["cursor"]
            else:
                print(f"获取历史记录失败，错误码：{r_json['code']}，错误信息：{r_json['message']}")
                return None
            time.sleep(random.uniform(0.2, 0.5))
            max_id = self.last_cursor["max"]
            business = self.last_cursor["business"]
            view_at = self.last_cursor["view_at"]
        print(f"\n最后一次的max_id='{max_id}', business'{business}', view_at='{view_at}'")
        print(f"找到的视频有{len(found_videos)}/{bv_count}个: {found_videos}")
        # 把video_stat保存在output/temp_失效视频.json
        with open("output/temp_失效视频.json", "w", encoding="utf-8") as f:
            json.dump(video_stat, f, ensure_ascii=False, indent=4)
        return video_stat


# b站的一些排行榜(目前建议只使用get_popular，其余的不太行的样子)
class biliRank:
    def __init__(self):
        self.headers = {
            "User-Agent": UserAgent().pcChrome,
            "Cookie": cookies().bilicookie,
        }
        self.headers_no_cookie = {
            "User-Agent": UserAgent().pcChrome,
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
            print(f"{i + 1}.{video['bvid']} {video['title']}")
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
            print(f"{i + 1}.{video['bvid']} {video['title']}")
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
    # biliA = biliArchive()
    # bvids = biliA.get_archives_list(2033914)
    # print(bvids)
    # biliM = biliMessage()
    # biliM.send_msg(3493133776062465, 506925078, "你好，请问是千年的爱丽丝同学吗？")
    biliL = BiliLogin()
    biliL.qr_login(save_name="cookie_大号")

    # full_path = 'cookie/cookie_大号.txt'  # 这里只是为了展示更改路径，实际使用时仍然建议使用默认路径cookie/qr_login.txt
    # biliH = biliHistory(cookie_path=full_path)
    # bv_list = ["BV1Bw4m1e7JR", "BV1j1g7eaE16", "BV1Vn4y1R7fH", "BV1Z1421k7nC", "BV194421D736", "BV1ihVteYEuZ",
    #            "BV1kM4m1S7na", "BV1WD421u71W", "BV1P1421C7A5", "BV1Xs421M7w6", "BV1AJ4m137hk", "BV1bNTvewEUB",
    #            "BV1VM4m1S7sv", "BV11y411b7Y4", "BV1Lz4y157vD", "BV1sS411w7Fk", "BV1aM4m127Ab"]
    # ans = biliH.get_invalid_video(bv_list, max_iter=100)
    # print(ans)
    # ans = biliH.get_invalid_video("BV1uS411N74G", max_iter=50)
    # print(ans)
    # success = biliH.get_history_all(max_iter=2)
    # # get_history_all最终输出结果里包含获得到上一次的信息，以方便下一次使用，如：
    # # 最后一次的max_id='1055866500', business='archive', view_at='1719150877'
    #
    # if success:
    #     biliH.log_history()
    #     biliH.save_video_history_df(view_info=True, detailed_info=True,
    #                                 save_path="output", save_name="history_xm", add_df=True)
    # else:
    #     print("获取历史记录失败")

    # biliV = biliVideo("BV1YS421d7Yx", cookie_path=full_path)
    # biliV.get_content()
    # print(biliV.tag)
    # print(biliV.tid, biliV.tname, biliV.time)

    # biliV = biliVideo("BV1ov42117yC", cookie_path=full_path)
    # s = biliV.get_user_action()
    # if s:
    #     print(biliV.user_like, biliV.user_coin, biliV.user_fav)
    # else:
    #     print("获取失败")
    pass
