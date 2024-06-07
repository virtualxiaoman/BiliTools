import re
import json
import time
import pandas as pd
import requests
import os
from PIL import Image
from io import BytesIO
import random

from Tools.config import useragent
from Tools.config import bilicookies as cookies
from Tools.util.Colorful_Console import ColoredText as CT


# BV号和AV号的转换
class BV2AV:
    def __init__(self):
        """转化算法来自于https://socialsisteryi.github.io/bilibili-API-collect/docs/misc/bvid_desc.html#python"""
        self.XOR_CODE = 23442827791579
        self.MASK_CODE = 2251799813685247
        self.MAX_AID = 1 << 51
        self.ALPHABET = "FcwAPNKTMug3GV5Lj7EJnHpWsx4tb8haYeviqBz6rkCy12mUSDQX9RdoZf"
        self.ENCODE_MAP = 8, 7, 0, 5, 1, 3, 2, 4, 6
        self.DECODE_MAP = tuple(reversed(self.ENCODE_MAP))

        self.BASE = len(self.ALPHABET)
        self.PREFIX = "BV1"
        self.PREFIX_LEN = len(self.PREFIX)
        self.CODE_LEN = len(self.ENCODE_MAP)

    def av2bv(self, aid: int) -> str:
        """
        [使用方法]:
            BV2AV().av2bv(111298867365120)  # 返回"BV1L9Uoa9EUx"
        :param aid: av号
        :return: bv号
        """
        self.bvid = [""] * 9
        tmp = (self.MAX_AID | aid) ^ self.XOR_CODE
        for i in range(self.CODE_LEN):
            self.bvid[self.ENCODE_MAP[i]] = self.ALPHABET[tmp % self.BASE]
            tmp //= self.BASE
        return self.PREFIX + "".join(self.bvid)

    def bv2av(self, bvid: str) -> int:
        """
        [使用方法]:
            BV2AV().bv2av("BV1L9Uoa9EUx")  # 返回111298867365120
        :param bvid: bv号
        :return: av号
        """
        assert bvid[:3] == self.PREFIX
        bvid = bvid[3:]
        tmp = 0
        for i in range(self.CODE_LEN):
            idx = self.ALPHABET.index(bvid[self.DECODE_MAP[i]])
            tmp = tmp * self.BASE + idx
        return (tmp & self.MASK_CODE) ^ self.XOR_CODE


# 获取鉴权参数
class AuthUtil:
    @staticmethod
    def get_dev_id():
        """
        获取设备ID(可以自行在浏览器中查看)
        [使用方法]:
            print(AuthUtil.get_dev_id())
        :return: 设备ID
        """
        b = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F']
        s = list("xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx")
        for i in range(len(s)):
            if s[i] == '-' or s[i] == '4':
                continue
            random_int = random.randint(0, 15)
            if s[i] == 'x':
                s[i] = b[random_int]
            else:
                s[i] = b[(3 & random_int) | 8]
        return ''.join(s)  # 得到B182F410-3865-46ED-840F-B58B71A78B5E这样的

    @staticmethod
    def get_timestamp():
        """
        获取时间戳
        [使用方法]:
            print(AuthUtil.get_timestamp())
        :return: 时间戳
        """
        return int(time.time())


# 获取b站登录状态(目前该功能只做了获取登录状态, todo:应该将biliLoginState与biliQRLogin合并)
class biliLoginState:
    def __init__(self, headers):
        """
        :param headers: 比如headers={"Cookie": cookies().bilicookie, "User-Agent": useragent().pcChrome}
        """
        self.headers = headers
        self.url = 'https://api.bilibili.com/x/web-interface/nav'

    def get_login_state(self):
        """
        获取登录状态
        [使用方法]:
            biliLoginState(headers).get_login_state()
        :return:
        """
        # get请求https://api.bilibili.com/x/web-interface/nav，参数是cookie，返回的是用户的信息
        r = requests.get(url=self.url, headers=self.headers)
        login_msg = r.json()
        print("登录状态：", login_msg["data"]["isLogin"])


# b站扫码登录(目前该功能没有实现)
class biliQRLogin:
    """B站扫码登录，目前该功能没有实现
    [示例代码]:
        QRL = biliQRLogin()
        QRL.require()
        QRL.generate()
        while True:
            status, cookie = QRL.scan_qr()
            match status:
                case 86090:
                    print("扫码成功但未确认")
                case 0:
                    print("登录成功")
                case 86101:
                    print("未扫码")
                case 86038:
                    print("二维码失效")
                    break
    """
    def __init__(self):
        self.headers = {"User-Agent": useragent().pcChrome}
        self.url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/generate'

    def require(self):
        r = requests.get(self.url, headers=self.headers)
        print(r.text)
        data = r.json()
        self.token = data['data']['qrcode_key']
        self.qrcode_url = data['data']['url']

    def generate(self):
        r = requests.get(self.qrcode_url, headers=self.headers)
        img = Image.open(BytesIO(r.content))
        img.show()
        print("请使用手机客户端扫描二维码登录...")

    def scan_qr(self):
        status = ''
        cookie = ''
        while True:
            url = f'https://passport.bilibili.com/x/passport-login/web/qrcode/poll?key={self.token}'
            response = requests.get(url)
            data = response.json().get('data', {})
            status = data.get('status')
            if status in ['ScanSuccess', 'Success']:
                cookie = response.headers.get('set-cookie')
            if status in ['ScanSuccess', 'Success', 'Timeout', 'Invalid']:
                break
            time.sleep(1)
        return status, cookie


# 获取b站视频信息(目前已实现获取视频信息、下载视频和音频功能)
class biliVideo:
    def __init__(self, bv, html_path=None):
        """
        [使用方法]:
            biliV = biliVideo("BV18x4y187DE")  # [必要]输入bv号
            biliV.get_html()  # [必要]获取html
            # biliV.get_content(download_mp4=True)  # [可选]下载视频
            biliV.get_content()  # [可选]不下载视频
            biliV.show_values()  # [非必要]显示视频信息
        :param bv: bv号
        :param html_path: 如不指定，则不存储。如指定，则为f"{self.html_path}{self.bv}.html"

        """
        # 基本信息
        self.bv = bv  # 你要爬取的视频的bv号
        self.html_path = html_path  # html存储路径
        self.url = f"https://www.bilibili.com/video/{self.bv}"
        self.headers = {
            "User-Agent": useragent().pcChrome,
            "Cookie": cookies().bilicookie,
            'referer': self.url
        }

        # 鉴权参数
        # cid是鉴权参数。请求https://api.bilibili.com/x/player/pagelist，参数是bv号，返回的是视频的cid
        self.cid = requests.get(url=f"https://api.bilibili.com/x/player/pagelist?bvid={self.bv}",
                                headers=self.headers).json()["data"][0]["cid"]  # 目前这个似乎只适用于单P视频，暂未验证

        # 网页文本
        self.rtext = None  # 网页的文本，也就是r.text

        # 基本信息
        self.aid = None  # 视频的av号
        self.bvid = None  # 视频的bv号，可以用来和bv号对比，看看有没有错误
        self.title = None  # 视频的标题
        self.pic = None  # 视频的封面路径
        self.desc = None  # 视频的简介
        self.stat = None  # 视频的统计数据，比如{'aid': 1003283555, 'view': 27847, 'danmaku': 76, 'reply': 143, 'favorite': 1458, 'coin': 201, 'share': 40, 'now_rank': 0, 'his_rank': 0, 'like': 1566, 'dislike': 0, 'evaluation': '', 'vt': 0, 'viewseo': 27847}
        self.view = None  # 视频的播放量
        self.dm = None  # 视频的弹幕量
        self.reply = None  # 视频的评论量
        self.time = None  # 视频的发布时间
        self.like = None  # 视频的点赞量
        self.coin = None  # 视频的投币量
        self.fav = None  # 视频的收藏量
        self.share = None  # 视频的转发量

        # 额外信息
        self.play_url = "https://api.bilibili.com/x/player/wbi/playurl"  # 视频下载信息的获取地址
        self.down_video_json = None  # 视频的下载信息（包含视频与音频地址，在download_video()与download_audio()中获取）

    def get_html(self):
        biliLoginState(self.headers).get_login_state()
        r = requests.get(url=self.url, headers=self.headers)
        r.encoding = 'utf-8'
        self.rtext = r.text
        if self.html_path is not None:
            if not os.path.exists(self.html_path):
                os.makedirs(self.html_path)
            with open(f"{self.html_path}{self.bv}.html", 'w', encoding='utf-8') as f:
                f.write(self.rtext)

    def get_content(self):
        """
        [使用方法]:
            biliV = biliVideo("BV18x4y187DE")
            biliV.get_html()  # [必要]获取html
            biliV.get_content()
        不能保证一定能用，获取view,dm的上个月还能用，这个月就不能用了，B站前端牛魔王又改了
        """
        if self.html_path is not None:
            with open(f"{self.html_path}{self.bv}.html", 'r', encoding='utf-8') as f:
                self.rtext = f.read()

        pattern_base_data = re.compile(r'window\.__INITIAL_STATE__=(.*?);\(function\(\)')
        base_data_match = re.search(pattern_base_data, self.rtext)

        if base_data_match:
            base_data_content = base_data_match.group(1)
            base_data_content = json.loads(base_data_content)
            self.aid = base_data_content['videoData']['aid']
            self.bvid = base_data_content['videoData']['bvid']
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

    def download_video(self, save_video_path=None, qn=80, platform="pc", high_quality=1, fnval=16):
        """
        [使用方法]:
            biliV = biliVideo("BV18x4y187DE")
            biliV.download_video()
        参数具体请查看 `BAC文档
        <https://socialsisteryi.github.io/bilibili-API-collect/docs/video/videostream_url.html>`__.
        :param save_video_path: 视频保存路径。路径为f"{save_video_path}{self.bv}.mp4"。如不指定，则保存在当前目录下f"{self.bv}.mp4"
        :param qn: 视频清晰度。80就是1080p，64就是720p。该值在DASH格式下无效，因为DASH会取到所有分辨率的流地址
        :param platform: 平台。pc或html5
        :param high_quality: 当platform=html5时，此值为1可使画质为1080p
        :param fnval: 1代表mp4，16是DASH。非常建议使用16。
        """
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
        r = requests.get(url=self.play_url, headers=self.headers, params=params)
        self.down_video_json = r.json()
        # print(self.down_video_json)
        if fnval == 1:
            video_content = requests.get(url=self.down_video_json["data"]["durl"][0]["url"], headers=self.headers).content
        else:
            video_content = requests.get(url=self.down_video_json["data"]["dash"]["video"][0]["baseUrl"],
                                         headers=self.headers).content
        self._save_mp4(video_content, save_video_path)

    def download_audio(self, save_audio_path=None, save_audio_name=None, fnval=16):
        """
        下载音频。如果视频音频都要，建议在download_video之后使用，这样能减少一次请求。
        [使用方法]:
            biliV = biliVideo("BV12a411k7os")
            biliV.download_audio(save_audio_path="output")
        :param save_audio_path: 音频保存路径
        :param save_audio_name: 音频保存名称
        :param fnval: 一般就是16了，原因请见download_video()里fnval参数的描述
        :return:
        """
        if self.down_video_json is None:
            params = {
                "bvid": self.bv,
                "cid": self.cid,
                "fnval": fnval
            }
            r = requests.get(url=self.play_url, headers=self.headers, params=params)
            self.down_video_json = r.json()
        # print(self.down_video_json)
        audio_content = requests.get(url=self.down_video_json["data"]["dash"]["audio"][0]["baseUrl"],
                                     headers=self.headers).content
        self._save_mp3(audio_content, save_audio_path, save_audio_name)

    def download_pic(self, save_pic_path=None, save_pic_name=None):
        """
        图片下载
        [使用方法]
            biliV = biliVideo("BV1Jv4y1p7q3")
            biliV.get_html()
            biliV.get_content()
            biliV.download_pic(save_pic_path="output", save_pic_name="BV1Jv4y1p7q3封面")
        :param save_pic_path: 图片保存路径
        :param save_pic_name: 图片保存名称
        :return:
        """
        if self.pic is None:
            self.get_content()
        if self.pic is None:
            print("图片地址获取失败，再见ヾ(￣▽￣)")
            return 114514
        print(self.pic)
        pic_content = requests.get(url=self.pic, headers=self.headers).content
        self._save_pic(pic_content, save_pic_path, save_pic_name)

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
            "av": [self.aid],
            "bv": [self.bvid],
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
        print(CT('av号: ').blue() + f"{self.aid}")
        print(CT('bv号: ').blue() + f"{self.bvid}")
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

    def _save_mp4(self, video_content, save_video_path=None, save_video_name=None):
        """
        [子函数]保存视频
        :param video_content: 视频内容，是get请求返回的二进制数据
        :param save_video_path: 视频保存路径
        :param save_video_name: 视频保存名称
        """
        # 如果地址不是以/结尾，就加上/
        if save_video_path is not None:
            if save_video_path[-1] != "/":
                save_video_path += "/"
        # 视频名
        if save_video_name is None:
            name = self.bv
        else:
            name = save_video_name
        # 保存视频
        if save_video_path is not None:
            with open(f"{save_video_path}{name}.mp4", 'wb') as f:
                f.write(video_content)
        else:
            with open(f"{name}.mp4", 'wb') as f:
                f.write(video_content)

    def _save_mp3(self, audio_content, save_audio_path=None, save_audio_name=None):
        """
        [子函数]保存音频
        :param audio_content: 音频内容，是get请求返回的二进制数据
        :param save_audio_path: 音频保存路径
        :param save_audio_name: 音频保存名称
        """
        # 如果地址不是以/结尾，就加上/
        if save_audio_path is not None:
            if save_audio_path[-1] != "/":
                save_audio_path += "/"
        # 音频名
        if save_audio_name is None:
            name = self.bv
        else:
            name = save_audio_name
        # 保存音频
        if save_audio_path is not None:
            with open(f"{save_audio_path}{name}.mp3", 'wb') as f:
                f.write(audio_content)
        else:
            with open(f"{name}.mp3", 'wb') as f:
                f.write(audio_content)

    def _save_pic(self, pic_content, save_pic_path=None, save_pic_name=None, save_type="jpg"):
        """
        [子函数]保存图片
        :param pic_content: 图片内容，是get请求返回的二进制数据
        :param save_pic_path: 图片保存路径
        :param save_pic_name: 图片保存名称
        :param save_type: 图片保存格式
        """
        # 如果地址不是以/结尾，就加上/
        if save_pic_path is not None:
            if save_pic_path[-1] != "/":
                save_pic_path += "/"
        # 图片名
        if save_pic_name is None:
            name = str(self.bv) + "的快照"
        else:
            name = save_pic_name
        # 保存图片
        if save_pic_path is not None:
            if not os.path.exists(save_pic_path):
                os.makedirs(save_pic_path)
            with open(f"{save_pic_path}{name}.{save_type}", 'wb') as f:
                f.write(pic_content)
        else:
            with open(f"{name}.{save_type}", 'wb') as f:
                f.write(pic_content)


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
            biliLoginState(self.headers).get_login_state()
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
            biliM.send_msg(506925078, 381978872, "催更[doge]")
        :param sender_uid: 发送者mid
        :param receiver_id: 接收者mid
        :param content: 内容
        :param msg_type: 消息类型。1:发送文字 2:发送图片 5:撤回消息
        :return:
        """
        url = 'https://api.vc.bilibili.com/web_im/v1/web_im/send_msg'
        dev_id = "B182F410-3865-46ED-840F-B58B71A78B5E"  # 设备id
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

    biliV = biliVideo("BV1Jv4y1p7q3")
    biliV.get_html()
    biliV.get_content()
    biliV.download_pic(save_pic_path="output", save_pic_name="BV1Jv4y1p7q3封面")

    # biliR = biliReply(bv="BV1Ss421M7VJ")
    # biliR.send_reply("兄弟你好香啊😋")

    pass



