"""
收藏夹服务。
取代旧 `src/archive.py` 中的 `BiliFav`（原文件把收藏夹与合集混在一起，已拆分）。
"""

import logging
from typing import Optional

from src.api.session import BiliSession
from src.models.fav_model import FavInfo
from src.urls.fav_urls import FavUrls

logger = logging.getLogger(__name__)


class FavService:
    """B 站收藏夹服务。

    后端只接收规范 media_id（int），不解析 URL；链接解析统一由前端完成后再传入。
    """

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    def _resolve_media_id(self, media_id: Optional[int]) -> int:
        """后端只接收规范 media_id（int 或数字字符串），不接受 URL。

        链接解析统一由前端（frontend.pyside6.utils）归一化后再传入。
        """
        if media_id is None:
            raise ValueError("需要提供 media_id")
        s = str(media_id).strip()
        if not s.isdigit():
            raise ValueError(f"media_id 必须是纯数字，收到：{media_id}")
        return int(s)

    def get_fav_info(self, media_id: Optional[int] = None) -> FavInfo:
        """获取收藏夹详情（名称/视频数量）。
        请求示例：
        https://api.bilibili.com/x/v3/fav/folder/info?media_id=3953119978
        返回值示例：
            {
              "code": 0,
              "message": "OK",
              "ttl": 1,
              "data": {
                "id": 3953119978,
                "fid": 39531199,
                "mid": 506925078,
                "attr": 22,
                "title": "走不出来的那些日子",
                "cover": "http://i2.hdslb.com/bfs/archive/577e9ad0937b46ae3c52601aeee517fd7f5876de.jpg",
                "upper": {
                  "mid": 506925078,
                  "name": "virtual小满",
                  "face": "https://i0.hdslb.com/bfs/face/ab7b6b46a2c358e914140a0d62ac3322cad44d4f.jpg",
                  "followed": false,
                  "vip_type": 1,
                  "vip_statue": 0
                },
                "cover_type": 2,
                "cnt_info": {
                  "collect": 0,
                  "play": 0,
                  "thumb_up": 0,
                  "share": 0
                },
                "type": 11,
                "intro": "",  # 收藏夹简介(这里没有简介)
                "ctime": 1768138225,
                "mtime": 1768138225,
                "state": 0,
                "fav_state": 0,
                "like_state": 0,
                "media_count": 4,  # 收藏夹内的视频数量
                "is_top": false,
                "is_kid_playlist": false,
                "kid_playlist_desc": ""
              }
            }

        :param media_id: 收藏夹 media_id（int）
        :return: FavInfo
        """
        mid = self._resolve_media_id(media_id)
        data = self.session.get(FavUrls.FOLDER_INFO, params={"media_id": mid})
        return FavInfo.from_dict(data)

    def get_fav_bv(self, media_id: Optional[int] = None) -> list:
        """获取收藏夹内的视频 BV 号列表（一次性返回全部，不截断）。
        请求示例：
        https://api.bilibili.com/x/v3/fav/resource/ids?media_id=3953119978
        （对应网址是https://space.bilibili.com/506925078/favlist?fid=3953119978）
        返回值示例：
            {
              "code": 0,
              "message": "OK",
              "ttl": 1,
              "data": [
                {
                  "id": 115972119724128,
                  "type": 2,
                  "bv_id": "BV1hr6EBBEAV",
                  "bvid": "BV1hr6EBBEAV"
                },
                {
                  "id": 761518527,
                  "type": 2,
                  "bv_id": "BV1z64y1b7H4",
                  "bvid": "BV1z64y1b7H4"
                },
                {
                  "id": 5306111,
                  "type": 2,
                  "bv_id": "BV1ts411y7FY",
                  "bvid": "BV1ts411y7FY"
                },
                {
                  "id": 114829893307654,
                  "type": 2,
                  "bv_id": "BV1AWGVztE8W",
                  "bvid": "BV1AWGVztE8W"
                }
              ]
            }
        [使用方法]:
            service = FavService()
            bvs = service.get_fav_bv(3953119978)

        :param media_id: 收藏夹 media_id（int）
        :return: 视频bv号列表
        """
        mid = self._resolve_media_id(media_id)
        data = self.session.get(FavUrls.RESOURCE_IDS, params={"media_id": mid})
        return [fav["bvid"] for fav in data]
