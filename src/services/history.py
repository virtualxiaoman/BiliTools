"""
历史记录服务：分页获取历史记录、查找失效视频、导出观看信息。

取代旧 `src/history.py` 的 `BiliHistory`：
- 分页逻辑统一在 `get_history_page`（一个游标翻页器），不再复制三份；
- 不在构造函数里发请求，构造即请求的问题消失；
- 返回 `HistoryPage`/`HistoryItem` 模型。
"""

import logging
import time
from pathlib import Path
from typing import Optional

from src.api.session import BiliSession
from src.config.path import HISTORY_OUTPUT_DIR
from src.models.history import HistoryPage
from src.urls.history import HistoryUrls
from src.util.filename import resolve_save_path

logger = logging.getLogger(__name__)


class HistoryService:
    """B 站历史记录服务。"""

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    # ---- 分页获取 ----

    def get_history_page(
        self,
        max_id: int = 0,
        business: str = "",
        view_at: int = 0,
        filter_type: str = "all",
        ps: int = 20,
    ) -> HistoryPage:
        """获取一页历史记录。

        :param max_id: 历史记录截止目标 id。稿件avid，剧集(番剧/影视)ssid，直播间id，文集rlid，文章cvid
        :param business: 历史记录截止目标业务类型。archive稿件，pgc剧集(番剧/影视), live直播, article-list文集, article文章
        :param view_at: 历史记录截止时间。默认为 0，为当前时间
        :param filter_type: 历史记录分类筛选。archive稿件，live直播，article文章
        :param ps: 每页项数。默认为 20，最大 30
        :return: HistoryPage（含下一页游标）
        """
        params = {
            "max": max_id,
            "business": business,
            "view_at": view_at,
            "type": filter_type,
            "ps": ps,
        }
        data = self.session.get(HistoryUrls.CURSOR, params=params)
        return HistoryPage.from_json(data)

    def get_history_all(self, max_iter: int = 5, filter_type: str = "all", ps: int = 20,
                        start: Optional[HistoryPage] = None) -> list:
        """获取多页历史记录（直到 max_iter 页或用完游标）。

        :param max_iter: 最多翻页数
        :param filter_type: 历史记录分类筛选
        :param ps: 每页项数
        :param start: 从指定游标继续翻页（上次获取的 HistoryPage）
        :return: HistoryItem 列表
        """
        page = start
        max_id = page.max if page else 0
        business = page.business if page else ""
        view_at = page.view_at if page else 0

        items = []
        for i in range(max_iter):
            logger.info("[HistoryService] 正在获取第 %d/%d 页历史记录", i + 1, max_iter)
            page = self.get_history_page(max_id=max_id, business=business, view_at=view_at,
                                         filter_type=filter_type, ps=ps)
            items.extend(page.items)
            if not page.has_more:
                break
            max_id, business, view_at = page.max, page.business, page.view_at
            time.sleep(0.3)
        return items

    # ---- 失效视频 ----

    def get_invalid_video(self, bv, max_iter: int = 10, ps: int = 20) -> list:
        """通过历史记录查找已失效（无法通过正常途径获取）的视频信息。

        [灵感来源]:
            在使用 get_history_all 的时候，因为发现视频
              BV1sS411w7Fk(卡拉彼丘香奈美泳装皮靶场实机演示)，
              BV1aM4m127Ab(炎热的夏天，柴郡当然要去玩水啦～)，
            已经失效，无法通过之前的正常途径获取，但是历史记录里其实保存了的。
            所以遍历历史记录去找到这些失效视频即可。

        :param bv: 视频BV号，可以是单个(str)，也可以是bv号列表(list)
        :param max_iter: 最大迭代次数，超过这个次数即使未找到也停止
        :param ps: 每页项数
        :return: 找到的失效视频历史条目（dict）列表
        """
        if max_iter <= 0:
            raise ValueError("max_iter不能小于或等于0")

        if not isinstance(bv, list):
            bv = [bv]
        remaining = set(bv)
        found = []

        page = self.get_history_page(filter_type="archive", ps=ps)
        for _ in range(max_iter):
            if not remaining:
                break
            for item in page.items:
                if item.bvid in remaining:
                    remaining.discard(item.bvid)
                    logger.info("[HistoryService] 已找到视频 %s 的历史记录，还剩 %d 个未找到",
                                item.bvid, len(remaining))
                    found.append(item.raw or {})
            if not page.has_more or not remaining:
                break
            page = self.get_history_page(max_id=page.max, business=page.business,
                                         view_at=page.view_at, filter_type="archive", ps=ps)
            time.sleep(0.3)

        logger.info("[HistoryService] 找到 %d/%d 个失效视频", len(found), len(bv))
        return found

    # ---- 导出 ----

    def save_video_history_df(self, items: Optional[list] = None, *, view_info: bool = False,
                              detailed_info: bool = False,
                              save_path: Optional[Path] = None,
                              save_name: str = "history",
                              add_df: bool = True):
        """保存历史记录中的视频信息到 xlsx。

        [说明] 相比旧实现：不再内部串行拉取每个视频详情（原 save_video_history_df 每次
        new BiliVideo 拉详情，慢且无重试）。这里改为「输入 HistoryItem 列表 + 可选详情数据」导出，
        详情数据由调用方决定如何获取（建议用 VideoService.fetch_info，可并发）。

        :param items: HistoryItem 列表。None 时调用 get_history_all() 获取默认 5 页
        :param view_info: 是否需要保存观看信息（点赞/投币/收藏）——需要传入已带 user_action 的详情
        :param detailed_info: 是否需要保存视频详细信息（标题/stat等）——需要传入已带详情的 items
        :param save_path: xlsx 保存目录。None 时用 HISTORY_OUTPUT_DIR
        :param save_name: xlsx 文件名（不含后缀）
        :param add_df: 文件存在时是否追加（默认 True）
        :return: DataFrame
        """
        import pandas as pd

        if items is None:
            items = self.get_history_all()

        archive_items = [it for it in items if it.business == "archive"]
        data = {
            "bv": [it.bvid for it in archive_items],
            "progress": [it.progress for it in archive_items],
            "duration": [it.duration for it in archive_items],
            "view_percent": [it.view_percent for it in archive_items],
            "view_time": [it.view_at for it in archive_items],
        }
        if view_info:
            data["u_like"] = [getattr(it, "u_like", "") for it in archive_items]
            data["u_coin"] = [getattr(it, "u_coin", "") for it in archive_items]
            data["u_fav"] = [getattr(it, "u_fav", "") for it in archive_items]
        if detailed_info:
            for key in ("title", "num_view", "num_dm", "num_reply", "pub_time",
                        "num_like", "num_coin", "num_fav", "num_share", "tags",
                        "tid", "up_name", "up_followers"):
                data[key] = [getattr(it, key, "") for it in archive_items]

        df = pd.DataFrame(data)
        save_dir = Path(save_path) if save_path is not None else HISTORY_OUTPUT_DIR
        save_dir.mkdir(parents=True, exist_ok=True)
        file_path = resolve_save_path(save_dir, f"{save_name}.xlsx")

        if file_path.exists() and add_df:
            df_old = pd.read_excel(file_path)
            df = pd.concat([df_old, df], axis=0)
            if "num_view" in df.columns:
                df = df.sort_values(by="num_view", ascending=False)
            df = df.drop_duplicates(subset=["bv"], keep="first")
            df = df.sort_values(by="view_time", ascending=False)

        df.to_excel(file_path, index=False)
        logger.info("[HistoryService] 历史记录已保存到 %s", file_path)
        return df
