import pandas as pd
import requests
import os

from src.login import BiliLogin
# from src.util.Colorful_Console import ColoredText as CT  # 用于控制台的彩色输出
from src.utils import BiliVideoUtil, AuthUtil  # B站视频工具
from src.config import UserAgent  # User-Agent
from src.config import BiliCookies as cookies  # B站cookie
from src.config import Config  # 加载配置信息


class VideoUrls:
    PLAY = "https://api.bilibili.com/x/player/wbi/playurl"
    VIEW = "https://api.bilibili.com/x/web-interface/view"
    VIEW_DETAIL = "https://api.bilibili.com/x/web-interface/view/detail"
    TAG = "https://api.bilibili.com/x/tag/archive/tags"

    @staticmethod
    def video(bvid: str) -> str:
        return f"https://www.bilibili.com/video/{bvid}"


# 获取b站视频信息(目前已实现获取视频信息，下载视频、音频、封面、快照功能)
# 对于不确定的视频，请务必先检查其属性值accessible是否为True，在biliVideo各个板块中不一定主动判断了该值。
class BiliVideo(BiliVideoUtil):
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

        self.wts, self.w_rid = AuthUtil().get_wbi()

        if cookie_path is None:
            cookie_path = Config.COOKIE_PATH
            # warning_text = "[此警告可忽略] cookie_path参数未指定，默认为 'cookie/qr_login.txt' ，请注意是否是所需要的cookie。"
            # modify_tip = '请修改为类似这样的参数传递：cookie_path="cookie/qr_login.txt"'
            # warnings.warn(warning_text + "[Tips]: " + modify_tip, stacklevel=1)

        self.url_bv = f"https://www.bilibili.com/video/{self.bv}"  # 视频链接
        self.url_play = "https://api.bilibili.com/x/player/wbi/playurl"  # 视频下载
        self.url_stat = f"https://api.bilibili.com/x/web-interface/view?bvid={self.bv}"  # 视频信息
        self.url_stat_detail = f"https://api.bilibili.com/x/web-interface/view/detail?bvid={self.bv}"  # 视频详细信息
        self.url_tag = "https://api.bilibili.com/x/tag/archive/tags"  # 视频标签
        self.url_up = "https://api.bilibili.com/x/web-interface/card"  # up主信息(简略)
        self.videoshot_url = "https://api.bilibili.com/x/player/videoshot"

        self.headers = {
            "User-Agent": UserAgent().pcChrome,
            "Cookie": cookies(path=cookie_path).bilicookie,
            # 'referer': self.url_bv,
            'referer': "https://www.bilibili.com",
            "Origin": "https://www.bilibili.com",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        }
        # print(self.headers)

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

    # 用于获取视频信息
    def get_content(self, stat=True, tag=True, up=True):
        """
        [使用方法]:
            biliV = BiliVideo("BV18x4y187DE")
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
                       full_path=None, qn=80, fnval=4048):
        """
        [使用方法]:
            biliV = BiliVideo("BV18x4y187DE")
            biliV.download_video()
        参数具体请查看 `BAC文档
        <https://socialsisteryi.github.io/bilibili-API-collect/docs/video/videostream_url.html>`_.
        :param save_video_path: 视频保存路径。路径为f"{save_video_path}{self.bv}.mp4"。如不指定，则保存在当前目录下f"{self.bv}.mp4"
        :param save_video_name: 视频保存名称。
        :param save_video_add_desc: 视频保存名称的附加描述
        :param full_path: 全路径名称(含路径、文件名、后缀)，指定此参数时，其余与路径相关的信息均失效。
        :return: 下载成功返回True，失败返回False(大部分情况是因为视频不存在)
        """
        self.check_path(save_video_path)
        if self.cid is None:
            return False
        params = {
            "bvid": self.bv,
            "cid": self.cid,
            "qn": 120,  # 视频清晰度。120就是4K，80就是1080p，64就是720p。该值在DASH格式下无效，因为DASH会取到所有分辨率的流地址
            "fnver": 0,  # 定值
            "fnval": 4048,  # 设置为4048则会所有可用 DASH 视频流。
            "fourk": 1,  # 是否允许4k。取0代表画质最高1080P（这是不传递fourk时的默认值），取1代表最高4K
            "platform": "pc",  # 平台。pc或html5
            "high_quality": 1,  # 当platform=html5时，此值为1可使画质为1080p
        }
        wts, w_rid = AuthUtil().get_wbi(params)
        print(f"params: {params}")
        print(wts, w_rid)
        print(self.wts, self.w_rid)

        r = requests.get(url=self.url_play, headers=self.headers, params=params)
        self.down_video_json = r.json()
        # print(self.down_video_json)
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
            biliV = BiliVideo("BV12a411k7os")
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
                "fnval": fnval,
                "wts": self.wts,
                "w_rid": self.w_rid,
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
            biliV = BiliVideo("BV1hi4y1e7B1")
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
            biliV = BiliVideo("BV1Jv4y1p7q3")
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
            biliv = BiliVideo("BV1zm411y7eF")
            biliv.download_videoshot(save_videoshot_path="output", save_videoshot_name="快照")
        :param save_videoshot_path: 视频快照保存路径。
        :param save_videoshot_name: 视频快照保存名称。保存的名字是f"{save_videoshot_path}{save_videoshot_name}_{i}.jpg"
        :param index: 是否需要视频快照的索引。默认为0表示不需要。
        :return: (list)视频快照地址
        """
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
            biliV = BiliVideo("BV1ov42117yC", cookie_path=full_path)
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
                biliV = BiliVideo(bvs)
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

    # # 显示视频信息
    # def show_values(self):
    #     print(CT('av号: ').blue() + f"{self.av}")
    #     print(CT('bv号: ').blue() + f"{self.bv}")
    #     print(CT('标题: ').blue() + f"{self.title}")
    #     print(CT('图片地址: ').blue() + f"{self.pic}")
    #     print(CT('简介: ').blue() + f"{self.desc}")
    #     print(CT('播放量: ').blue() + f"{self.view}")
    #     print(CT('弹幕数: ').blue() + f"{self.dm}")
    #     print(CT('评论数: ').blue() + f"{self.reply}")
    #     print(CT('发布时间: ').blue() + f"{self.time}")
    #     print(CT('点赞数: ').blue() + f"{self.like}")
    #     print(CT('硬币数: ').blue() + f"{self.coin}")
    #     print(CT('收藏数: ').blue() + f"{self.fav}")
    #     print(CT('分享数: ').blue() + f"{self.share}")
    #     print(CT('标签: ').blue() + f"{self.tag}")
    #     print(CT('分区tid: ').blue() + f"{self.tid}")
    #     print(CT('子分区名称: ').blue() + f"{self.tname}")
    #     print(CT('up主: ').blue() + f"{self.up}")
    #     print(CT('up主mid: ').blue() + f"{self.up_mid}")
    #     print(CT('是否关注up主: ').blue() + f"{self.up_follow}")
    #     print(CT('up主粉丝数: ').blue() + f"{self.up_followers}")
    #     print(CT('是否点赞: ').blue() + f"{self.user_like}")
    #     print(CT('投币数量: ').blue() + f"{self.user_coin}")
    #     print(CT('是否收藏: ').blue() + f"{self.user_fav}")


if __name__ == '__main__':
    # biliM = biliMessage()
    # biliM.send_msg(506925078, 381978872, "催更[doge]")

    # biliV = BiliVideo("BV1ov42117yC")
    # biliV.get_html()
    # biliV.get_content()
    # biliV.download_pic(save_pic_path="output", save_pic_name="BV1ov42117yC封面")

    # biliL = BiliLogin()
    # biliL.qr_login()
    # headers = {
    #     "User-Agent": useragent().pcChrome,
    #     "Cookie": cookies(path='cookie/qr_login.txt').bilicookie,
    #     'referer': "https://www.bilibili.com"
    # }
    # BiliLogin(headers).get_login_state()
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

    # biliV = BiliVideo("BV1YS421d7Yx", cookie_path=full_path)
    # biliV.get_content()
    # print(biliV.tag)
    # print(biliV.tid, biliV.tname, biliV.time)

    # biliV = BiliVideo("BV1ov42117yC", cookie_path=full_path)
    # s = biliV.get_user_action()
    # if s:
    #     print(biliV.user_like, biliV.user_coin, biliV.user_fav)
    # else:
    #     print("获取失败")
    pass
