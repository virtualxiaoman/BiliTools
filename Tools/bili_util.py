# Author: virtual小满
# 功能：B站工具。包括BV号和AV号的转换，获取鉴权参数，获取视频信息等

import random
import time
import os
import requests
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips

from Tools.config import useragent  # User-Agent
from Tools.config import bilicookies as cookies  # B站cookie


# BV号和AV号的转换
class BV2AV:
    def __init__(self):
        """转化算法来自于 `BAC文档
        <https://socialsisteryi.github.io/bilibili-API-collect/docs/misc/bvid_desc.html#python>`_."""
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


# B站视频信息工具
class BiliVideoUtil:
    def __init__(self, bv=None, av=None, headers=None):
        """
        初始化bv,av,cid，并检测传入参数的合法性
        [Tips]:
            建议所有的子类里参数bv都要在av前面，将bv作为主要的使用参数
        :param bv: bv号
        :param av: av号
        :param headers: 请求头
        """
        self.accessible = False
        self.bv = None
        self.av = None
        self.cid = None
        self.headers = None
        self.url = "https://www.bilibili.com/"  # 主站链接
        self.__init_params(bv, av, headers)

    def merge_video_audio(self, video_path, audio_path, save_path=None):
        """
        [子函数]合并视频和音频
        [Tips]:
            均需要完整路径
        :param video_path: 视频路径
        :param audio_path: 音频路径
        :param save_path: 合并后的视频保存路径
        """
        # 检查ffmpeg是否安装
        if os.system("ffmpeg -version") != 0:
            print("ffmpeg未安装")
            # 使用其他方法
            video_clip = VideoFileClip(video_path)
            audio_clip = AudioFileClip(audio_path)
            video_with_audio = video_clip.set_audio(audio_clip)
            video_with_audio.write_videofile(save_path, codec='libx264', audio_codec='aac')
        else:
            # 为了防止路径中有空格等ffmpeg不支持字符，使用双引号
            os.system(f'ffmpeg -i "{video_path}" -i "{audio_path}" -c:v copy -c:a flac "{save_path}"')

    def check_path(self, path):
        """
        [子函数]检查路径是否存在，不存在则创建
        :param path: 路径
        """
        # 如果传入的是一个path，就只要检查这个path是否存在，不存在则创建。如果传入的是list，就检查每个path是否存在，不存在则创建
        if isinstance(path, str):
            if not os.path.exists(path) and path is not None:
                os.makedirs(path)
        elif isinstance(path, list):
            for p in path:
                if not os.path.exists(p) and p is not None:
                    os.makedirs(p)
        elif path is None:
            pass
        else:
            raise ValueError("path参数类型错误")

    def _save_mp4(self, video_content, save_video_path=None, save_video_name=None, add_desc="视频(无音频)", full_path=None):
        """
        [子函数]保存视频
        :param video_content: 视频内容，是get请求返回的二进制数据
        :param save_video_path: 视频保存路径
        :param save_video_name: 视频保存名称
        :param add_desc: 额外描述，默认是"视频(无音频)"
        :param full_path: 全路径名称(含路径、文件名、后缀)，指定此参数时，其余与路径相关的信息均失效
        """
        video_path = self._get_path(save_video_path, save_video_name, add_desc=add_desc, save_type="mp4", full_path=full_path)
        if save_video_path is not None and not os.path.exists(save_video_path):
            os.makedirs(save_video_path)
        with open(video_path, 'wb') as f:
            f.write(video_content)

    def _save_mp3(self, audio_content, save_audio_path=None, save_audio_name=None, add_desc="音频", full_path=None):
        """
        [子函数]保存音频
        :param audio_content: 音频内容，是get请求返回的二进制数据
        :param save_audio_path: 音频保存路径
        :param save_audio_name: 音频保存名称
        :param add_desc: 额外描述，默认是"音频"
        :param full_path: 全路径名称(含路径、文件名、后缀)，指定此参数时，其余与路径相关的信息均失效
        """
        audio_path = self._get_path(save_audio_path, save_audio_name, add_desc=add_desc, save_type="mp3", full_path=full_path)
        if save_audio_path is not None and not os.path.exists(save_audio_path):
            os.makedirs(save_audio_path)
        with open(audio_path, 'wb') as f:
            f.write(audio_content)

    def _save_pic(self, pic_content, save_pic_path=None, save_pic_name=None, add_desc="封面", save_type="jpg", full_path=None):
        """
        [子函数]保存图片
        :param pic_content: 图片内容，是get请求返回的二进制数据
        :param save_pic_path: 图片保存路径
        :param save_pic_name: 图片保存名称
        :param add_desc: 额外描述，默认是"封面"
        :param save_type: 图片保存格式
        :param full_path: 全路径名称(含路径、文件名、后缀)，指定此参数时，其余与路径相关的信息均失效
        """
        pic_path = self._get_path(save_pic_path, save_pic_name, add_desc=add_desc, save_type=save_type, full_path=full_path)
        if save_pic_path is not None and not os.path.exists(save_pic_path):
            os.makedirs(save_pic_path)
        with open(pic_path, 'wb') as f:
            f.write(pic_content)

    def _get_path(self, path, name=None, add_desc=None, save_type='mp4', full_path=None):
        """
        [子函数]获取路径
            当name为None时，保存的是 path + bv + add_desc + save_type
            当name不为None时，保存的是 path + name + save_type
        :param path: 保存路径
        :param name: 文件名，默认为bv号
        :param add_desc: 额外描述，如"视频(无音频)"，"音频"，"图片"，"封面"等，默认不加
        :param save_type: 保存类型，如"mp4"，"mp3"，"jpg"等，默认为"mp4
        :return:
        """
        if full_path is None:
            name = self.bv + (add_desc if add_desc is not None else '') if name is None else name
            full_path = os.path.join(path, f"{name}.{save_type}") if path is not None else f"{name}.{save_type}"
        return full_path

    def __init_params(self, bv, av, headers):
        """
        初始化参数bv, av ,cid, headers，检验参数的合法性
        """
        # 检查参数的合法性
        if av is None and bv is None:
            raise ValueError("av和bv不能同时为空")
        elif av is not None and bv is not None:
            bv2av = BV2AV().bv2av(bv)
            if av != bv2av:
                raise ValueError(f"av和bv不对应，av={av}, bv={bv}")
        # 根据av得到bv
        elif av is not None:
            self.av = av
            self.bv = BV2AV().av2bv(self.av)
        # 根据bv得到av
        elif bv is not None:
            # 如果BV号以bv开头，则改为BV开头
            if bv[:2] == "bv":
                self.bv = "BV" + bv[2:]
            else:
                self.bv = bv
            self.av = BV2AV().bv2av(self.bv)
        else:
            raise ValueError("该分支理论上不会出现")

        # 设置headers
        if headers is None:
            self.headers = {
                "User-Agent": useragent().pcChrome,
                "Cookie": cookies().bilicookie,
                'referer': self.url
            }
        else:
            self.headers = headers

        # 检查视频是否可访问
        params = {
            "bvid": self.bv
        }
        r = requests.get("https://api.bilibili.com/x/web-interface/view", params=params, headers=self.headers)
        r_json = r.json()
        if r_json["code"] != 0:
            self.accessible = False
            print(f"[BiliVideoUtil-__init_params]获取视频信息失败，错误信息：{r_json['message']}")
            return False
        else:
            self.accessible = True

        # 获取cid
        url_cid = f"https://api.bilibili.com/x/player/pagelist?bvid={self.bv}"
        try:
            self.cid = requests.get(url=url_cid, headers=self.headers).json()["data"][0]["cid"]  # 目前这个似乎只适用于单P视频，暂未验证
        except Exception as e:
            print(f"[BiliVideoUtil-__init_params]获取cid失败，错误信息：{e}")

