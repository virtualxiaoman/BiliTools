import requests

from src.config import UserAgent, BiliCookies as cookies
from src.login import BiliLogin


# b站收藏夹(目前已实现获取收藏夹视频功能)
class BiliFav:
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
class BiliArchive:
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
