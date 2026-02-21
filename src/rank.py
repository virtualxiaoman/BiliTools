import requests

from src.config import UserAgent, BiliCookies as cookies


# b站的一些排行榜(目前建议只使用get_popular，其余的不太行的样子)
class BiliRank:
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
