"""
视频合集服务。
取代旧 `src/archive.py` 中的 `BiliArchive`（原文件把收藏夹与合集混在一起，已拆分）。

说明：`seasons_archives_list` 接口需要完整的 `page_num`/`page_size` 参数，
缺任一参数会返回 -400（旧代码因此误判为接口失效）。
"""

import logging
from typing import Optional

from src.api.auth import get_wbi
from src.api.session import BiliSession
from src.urls.archive_urls import ArchiveUrls

logger = logging.getLogger(__name__)


class ArchiveService:
    """B 站视频合集服务。"""

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    def _list_seasons(self, mid: int, page_num: int = 1, page_size: int = 10) -> list:
        """获取用户的全部合集（seasons_list）。

        [注意] 此接口仅能查询**任意用户**的合集列表（不需登录身份），
        但返回的每条合集结构较简略（meta + archives 视频列表，无分P信息）。

        在meta里面有season_id和name可供遍历的时候使用。
        meta里的total是该sid对应合集内的视频总数，不是mid对应用户所拥有的合集总数。

        返回值示例：
            [{'archives': [{'aid': 745944958,
                            'bvid': 'BV17k4y1w7fW',
                            'ctime': 1694658027,
                            'duration': 430,
                            'enable_vt': False,
                            'interactive_video': False,
                            'is_lesson_video': 0,
                            'pic': 'http://i0.hdslb.com/bfs/archive/2fa604c407685d45d76fafad3ba8ba752ca6b8bb.jpg',
                            'playback_position': 0,
                            'pubdate': 1694658026,
                            'stat': {'danmaku': 0, 'view': 239, 'vt': 0},
                            'state': 0,
                            'title': '【不义之财】明日方舟CV-EX-8突袭强杀',
                            'ugc_pay': 0,
                            'vt_display': ''},
                           {'aid': 491674378,
                            'bvid': 'BV16N411E7tW',
                            'ctime': 1696216326,
                            'duration': 404,
                            'enable_vt': False,
                            'interactive_video': False,
                            'is_lesson_video': 0,
                            'pic': 'http://i0.hdslb.com/bfs/archive/6f1ed567c85a4770bee875e11dec1a51337cb95a.jpg',
                            'playback_position': 0,
                            'pubdate': 1696216326,
                            'stat': {'danmaku': 1, 'view': 166, 'vt': 0},
                            'state': 0,
                            'title': '【明日方舟】纷争演绎A-3 小羊铃兰提丰叔叔苇草',
                            'ugc_pay': 0,
                            'vt_display': ''},
                           {'aid': 580967710,
                            'bvid': 'BV1M64y1K7SN',
                            'ctime': 1704701223,
                            'duration': 251,
                            'enable_vt': False,
                            'interactive_video': False,
                            'is_lesson_video': 0,
                            'pic': 'http://i0.hdslb.com/bfs/archive/f5a9a9fa4ec305d31d9e08becab17fc4cd6ba7cb.jpg',
                            'playback_position': 0,
                            'pubdate': 1704701223,
                            'stat': {'danmaku': 0, 'view': 447, 'vt': 0},
                            'state': 0,
                            'title': '千嶂边城300-400杀 没看到棘刺死了，还好提丰牛',
                            'ugc_pay': 0,
                            'vt_display': ''},
                           {'aid': 1051536720,
                            'bvid': 'BV1aH4y157tD',
                            'ctime': 1710322108,
                            'duration': 266,
                            'enable_vt': False,
                            'interactive_video': False,
                            'is_lesson_video': 0,
                            'pic': 'http://i0.hdslb.com/bfs/archive/1504f1d8203ea0f72baa3563525a684bde23a265.jpg',
                            'playback_position': 0,
                            'pubdate': 1710322108,
                            'stat': {'danmaku': 0, 'view': 148, 'vt': 0},
                            'state': 0,
                            'title': '[初见杀]人之光辉 11难0/41望周知',
                            'ugc_pay': 0,
                            'vt_display': ''},
                           {'aid': 1152673900,
                            'bvid': 'BV1RZ421v7zo',
                            'ctime': 1712048624,
                            'duration': 395,
                            'enable_vt': False,
                            'interactive_video': False,
                            'is_lesson_video': 0,
                            'pic': 'http://i0.hdslb.com/bfs/archive/b303cdcfae3080497eaca27551a77a81dd6486d5.jpg',
                            'playback_position': 0,
                            'pubdate': 1712048624,
                            'stat': {'danmaku': 0, 'view': 174, 'vt': 0},
                            'state': 0,
                            'title': '[潮曦作战 710分]小羊伟大无需多言！ 无限定/图图/莱伊/小莫/灵知',
                            'ugc_pay': 0,
                            'vt_display': ''},
                           {'aid': 1305771223,
                            'bvid': 'BV1KM4m1m7Nv',
                            'ctime': 1719315774,
                            'duration': 478,
                            'enable_vt': False,
                            'interactive_video': False,
                            'is_lesson_video': 0,
                            'pic': 'http://i0.hdslb.com/bfs/archive/f90a2fb5af788db203127165524058bb87428d3f.jpg',
                            'playback_position': 0,
                            'pubdate': 1719315774,
                            'stat': {'danmaku': 0, 'view': 108, 'vt': 0},
                            'state': 0,
                            'title': '观看空想花庭有脑子的记录',
                            'ugc_pay': 0,
                            'vt_display': ''}],
              'meta': {'category': 0,
                       'cover': 'https://archive.biliimg.com/bfs/archive/2fa604c407685d45d76fafad3ba8ba752ca6b8bb.jpg',
                       'description': '',
                       'mid': 506925078,
                       'name': '合集·明日方舟',
                       'ptime': 1785555540,
                       'season_id': 1717000,
                       'title': '明日方舟',
                       'total': 18},
              'recent_aids': [745944958,
                              491674378,
                              580967710,
                              1051536720,
                              1152673900,
                              1305771223]},
             {'archives': 同上
            ]
        :param mid: 用户UID
        :param page_num: 页码
        :param page_size: 每页数量
        :return: 合集列表，每条含 meta(season_id/name) 与 archives(视频列表)
        """
        params = {"mid": mid, "page_num": page_num, "page_size": page_size}
        get_wbi(params)
        data = self.session.get(ArchiveUrls.SEASONS_SERIES_LIST, params=params)
        return data.get("items_lists", {}).get("seasons_list", [])

    def get_season_by_sid(self, season_id: int, mid: int = 0) -> dict:
        """按 season_id 获取合集详情（meta + 完整视频列表）。

        [注意] 该接口需要完整的 page_num/page_size 参数，缺任一返回 -400。
        mid 不要求是登录用户（任意 UP 主的合集都能查），但传入 mid 能帮助定位。

        请求示例：https://api.bilibili.com/x/polymer/web-space/seasons_archives_list?mid=1&season_id=8344962&page_num=1&page_size=50
        返回值示例：
            {
              "code": 0,
              "message": "OK",
              "ttl": 1,
              "data": {
                "aids": [116748300912314, 116311271148738, 115988880164830],
                "archives": [
                  {
                    "aid": 116748300912314,
                    "bvid": "BV14sJP63EGu",
                    "ctime": 1781437909,
                    "duration": 1964,
                    "enable_vt": false,
                    "interactive_video": false,
                    "pic": "http://i1.hdslb.com/bfs/archive/9a8d743ecd23f9b2ae51f8e3e91f8e7d8458530d.jpg",
                    "playback_position": 0,
                    "pubdate": 1781438400,
                    "stat": {
                      "view": 1379,
                      "vt": 0,
                      "danmaku": 28
                    },
                    "state": 0,
                    "title": "【星尘】2026年3-5月春季歌曲推荐收录刊✡",
                    "ugc_pay": 0,
                    "vt_display": "",
                    "is_lesson_video": 0
                  },
                  {
                    "aid": 116311271148738,
                    "bvid": "BV1kQXSBLEo6",
                    "ctime": 1774769369,
                    "duration": 1408,
                    "enable_vt": false,
                    "interactive_video": false,
                    "pic": "http://i1.hdslb.com/bfs/archive/9ffec29f34600e40b106a905eb0a00c2914ea032.jpg",
                    "playback_position": 0,
                    "pubdate": 1774771200,
                    "stat": {
                      "view": 1875,
                      "vt": 0,
                      "danmaku": 10
                    },
                    "state": 0,
                    "title": "【星尘】2026年1-2月歌曲推荐收录刊✡",
                    "ugc_pay": 0,
                    "vt_display": "",
                    "is_lesson_video": 0
                  },
                  {
                    "aid": 115988880164830,
                    "bvid": "BV1CK62BKEcX",
                    "ctime": 1769850352,
                    "duration": 3511,
                    "enable_vt": false,
                    "interactive_video": false,
                    "pic": "http://i2.hdslb.com/bfs/archive/7531427cfffc47fc7ebc6de687fb08be2fc9feaf.jpg",
                    "playback_position": 0,
                    "pubdate": 1769858100,
                    "stat": {
                      "view": 11184,
                      "vt": 0,
                      "danmaku": 50
                    },
                    "state": 0,
                    "title": "✡来解锁2025尘厨年度报告吧✡",
                    "ugc_pay": 0,
                    "vt_display": "",
                    "is_lesson_video": 0
                  }
                ],
                "meta": {
                  "category": 0,
                  "cover": "https://archive.biliimg.com/bfs/archive/36b172ffdedfcf399876424ad7e2835fb74d03b6.jpg",
                  "description": "聆听星星之声🎵",
                  "mid": 1208038011,
                  "name": "合集·✡星星波动观测中心✡",
                  "ptime": 1781438400,
                  "season_id": 8344962,
                  "total": 3,
                  "title": "✡星星波动观测中心✡"
                },
                "page": {
                  "page_num": 1,
                  "page_size": 50,
                  "total": 3
                }
              }
            }

        :param season_id: 合集 sid
        :param mid: 合集所属用户UID。为 0 时尝试使用当前登录用户 mid
        :return: dict，含 meta(合集信息) 与 archives(视频列表)
        :raises ValueError: 合集不存在或无法解析
        """
        # if not mid:
        #     from src.services.login import LoginService
        #     mid = LoginService(self.session).get_mid() or 0
        # params = {"mid": mid, "season_id": season_id, "page_num": 1, "page_size": 50}
        # data = self.session.get(ArchiveUrls.SEASONS_ARCHIVES_LIST, params=params)
        # if not data or not data.get("archives"):
        #     raise ValueError(f"合集 {season_id} 不存在或没有视频。")
        # return data
        if not mid:
            from src.services.login import LoginService
            mid = LoginService(self.session).get_mid() or 0

        page_num = 1
        page_size = 50
        all_archives = []
        meta = None

        while True:
            params = {
                "mid": mid,
                "season_id": season_id,
                "page_num": page_num,
                "page_size": page_size,
            }
            data = self.session.get(ArchiveUrls.SEASONS_ARCHIVES_LIST, params=params)

            if not data:
                break

            if meta is None:
                meta = data.get("meta")
            archives = data.get("archives", [])
            all_archives.extend(archives)
            page = data.get("page", {})
            total = page.get("total", 0)

            if len(all_archives) >= total:
                break  # 已经获取全部视频
            if not archives:
                break  # 本页没有数据，避免死循环

            page_num += 1

        if not all_archives:
            raise ValueError(f"合集 {season_id} 不存在或没有视频。")

        return {
            "aids": [archive["aid"] for archive in all_archives],
            "archives": all_archives,
            "meta": meta,
            "page": {
                "page_num": 1,
                "page_size": len(all_archives),
                "total": len(all_archives),
            },
        }

    def get_bvlist_by_sid(self, season_id: int, mid: int = 0) -> list:
        """获取指定合集内视频的 BV 号列表。

        [使用方法]:
            service = ArchiveService()
            # 和纱猫猫小剧场, url: https://space.bilibili.com/37507923/channel/collectiondetail?sid=2033914
            bvids = service.get_archives_list(2033914)
            print(bvids)

        :param season_id: 合集 sid
        :param mid: 合集所属用户UID。0 时尝试用当前登录用户 mid
        :return: 视频bv号列表
        """
        data = self.get_season_by_sid(season_id, mid)
        return [archive["bvid"] for archive in data.get("archives", [])]

    def get_sidlist_by_mid(self, mid: int) -> list[int]:
        """获取用户全部合集的 season_id 列表。

        使用示例：
        ArchiveService().get_sidlist_by_mid(mid=506925078)
        返回值（13个sid）：
        [1717000, 8683221, 2215888, 7875133, 7674572, 7619345, 7261371, 4233568, 2903066, 2676364, 2161697, 1979242, 610731]

        :param mid: 用户 UID
        :return: 合集 season_id 列表
        """
        sid_list = []
        page_num = 1
        page_size = 10
        while True:
            # print(f"正在获取用户 {mid} 的合集列表，页码 {page_num}...")
            seasons = self._list_seasons(mid, page_num=page_num)
            if not seasons:
                break
            sid_list.extend(season["meta"]["season_id"]
                            for season in seasons if season.get("meta", {}).get("season_id"))

            if len(seasons) < page_size:
                break
            page_num += 1

        return sid_list
