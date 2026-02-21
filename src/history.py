import json
import os
import random
import time
import warnings
import pandas as pd
import requests

from src.video import BiliVideo
from src.config import UserAgent, Config
from src.config import BiliCookies as cookies


# b站历史记录
class BiliHistory:
    def __init__(self, cookie_path=Config.COOKIE_PATH):
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
        :param detailed_info: 是否需要额外保存详细信息：视频的各种stat，具体请见下面的代码或者是BiliVideo中实现的属性。
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
            biliV = BiliVideo(bv, cookie_path=self.cookie_path)
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
