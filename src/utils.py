# Author: virtual小满
# 功能：B站工具。包括BV号和AV号的转换，获取鉴权参数，获取视频信息等

import random
import time
import os
import requests
from functools import reduce
from hashlib import md5
import urllib.parse

from src.config import UserAgent  # User-Agent
from src.config import BiliCookies as Cookies  # B站cookie
from src.config import Config  # 配置文件


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

    def get_Wbi(self):
        img_key, sub_key = self._getWbiKeys()
        signed_params = self._encWbi(
            params={
                'foo': '114',
                'bar': '514',
                'baz': 1919810
            },
            img_key=img_key,
            sub_key=sub_key
        )
        wts = signed_params.get('wts')
        w_rid = signed_params.get('w_rid')
        # 如果希望 wts 是整数：
        if wts is not None:
            wts = int(wts)
        return wts, w_rid

    @staticmethod
    def _getMixinKey(orig: str):
        """对 imgKey 和 subKey 进行字符顺序打乱编码"""
        mixinKeyEncTab = [
            46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
            33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
            61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
            36, 20, 34, 44, 52
        ]
        return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, '')[:32]

    def _encWbi(self, params: dict, img_key: str, sub_key: str):
        """为请求参数进行 wbi 签名"""
        mixin_key = self._getMixinKey(img_key + sub_key)
        curr_time = round(time.time())
        params['wts'] = curr_time  # 添加 wts 字段
        params = dict(sorted(params.items()))  # 按照 key 重排参数
        # 过滤 value 中的 "!'()*" 字符
        params = {
            k: ''.join(filter(lambda chr: chr not in "!'()*", str(v)))
            for k, v
            in params.items()
        }
        query = urllib.parse.urlencode(params)  # 序列化参数
        wbi_sign = md5((query + mixin_key).encode()).hexdigest()  # 计算 w_rid
        params['w_rid'] = wbi_sign
        return params

    @staticmethod
    def _getWbiKeys() -> tuple[str, str]:
        """获取最新的 img_key 和 sub_key"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/58.0.3029.110 Safari/537.3',
            'Referer': 'https://www.bilibili.com/'
        }
        resp = requests.get('https://api.bilibili.com/x/web-interface/nav', headers=headers)
        resp.raise_for_status()
        json_content = resp.json()
        img_url: str = json_content['data']['wbi_img']['img_url']
        sub_url: str = json_content['data']['wbi_img']['sub_url']
        img_key = img_url.rsplit('/', 1)[1].split('.')[0]
        sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
        return img_key, sub_key


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

    @staticmethod
    def merge_video_audio(video_path, audio_path, save_path=None):
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
            return -1
        else:
            # 为了防止路径中有空格等ffmpeg不支持字符，使用双引号
            os.system(f'ffmpeg -i "{video_path}" -i "{audio_path}" -c:v copy -c:a flac "{save_path}"')

    @staticmethod
    def check_path(path):
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

    def _save_mp4(self, video_content, save_video_path=None, save_video_name=None, add_desc="视频(无音频)",
                  full_path=None):
        """
        [子函数]保存视频
        :param video_content: 视频内容，是get请求返回的二进制数据
        :param save_video_path: 视频保存路径
        :param save_video_name: 视频保存名称
        :param add_desc: 额外描述，默认是"视频(无音频)"
        :param full_path: 全路径名称(含路径、文件名、后缀)，指定此参数时，其余与路径相关的信息均失效
        """
        video_path = self._get_path(save_video_path, save_video_name, add_desc=add_desc, save_type="mp4",
                                    full_path=full_path)
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
        audio_path = self._get_path(save_audio_path, save_audio_name, add_desc=add_desc, save_type="mp3",
                                    full_path=full_path)
        if save_audio_path is not None and not os.path.exists(save_audio_path):
            os.makedirs(save_audio_path)
        with open(audio_path, 'wb') as f:
            f.write(audio_content)

    def _save_pic(self, pic_content, save_pic_path=None, save_pic_name=None, add_desc="封面", save_type="jpg",
                  full_path=None):
        """
        [子函数]保存图片
        :param pic_content: 图片内容，是get请求返回的二进制数据
        :param save_pic_path: 图片保存路径
        :param save_pic_name: 图片保存名称
        :param add_desc: 额外描述，默认是"封面"
        :param save_type: 图片保存格式
        :param full_path: 全路径名称(含路径、文件名、后缀)，指定此参数时，其余与路径相关的信息均失效
        """
        pic_path = self._get_path(save_pic_path, save_pic_name, add_desc=add_desc, save_type=save_type,
                                  full_path=full_path)
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
                "User-Agent": UserAgent().pcChrome,
                "Cookie": Cookies().bilicookie,
                'referer': self.url
            }
        else:
            self.headers = headers

        retry_count = 0
        # 检查视频是否可访问
        params = {
            "bvid": self.bv
        }
        while retry_count < Config.MAX_RETRY:
            r = requests.get("https://api.bilibili.com/x/web-interface/view", params=params, headers=self.headers)
            r_json = r.json()
            if r_json["code"] != 0:
                self.accessible = False
                retry_count += 1
                print(
                    f"[BiliVideoUtil-__init_params]第{retry_count}次获取视频{self.bv}是否可访问的信息失败，错误信息：{r_json['message']}")
                time.sleep(Config.RETRY_DELAY)
            else:
                self.accessible = True
                break

        retry_count = 0
        # 获取cid
        url_cid = f"https://api.bilibili.com/x/player/pagelist?bvid={self.bv}"
        while retry_count < Config.MAX_RETRY:
            r = requests.get(url=url_cid, headers=self.headers)
            r_json = r.json()
            if r_json["code"] != 0:
                retry_count += 1
                print(
                    f"[BiliVideoUtil-__init_params]第{retry_count}次获取{self.bv}的cid失败，错误信息：{r_json['message']}")
                time.sleep(Config.RETRY_DELAY)
            else:
                self.cid = r_json["data"][0]["cid"]  # 目前这个似乎只适用于单P视频，暂未验证
                break
