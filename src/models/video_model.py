"""
视频相关的数据模型（dataclass）。

设计说明：用类型化 dataclass 取代旧 `BiliVideo` 手写的 20+ 个属性。
命名统一使用 `num_*` 前缀表达「数量」类数据信息（如 dm -> num_dm）。

`from_*_json` 类方法用于从 B 站 API 响应的 data 字段直接构造模型。
"""

from dataclasses import dataclass, field
from typing import Optional

from src.models.download_model import DashStreams


@dataclass
class VideoStat:
    """视频统计数据（旧 BiliVideo 的 stat 相关字段，命名为 num_*）。"""

    num_view: int = 0  # 播放量（原 view）
    num_dm: int = 0  # 弹幕量（原 dm）
    num_reply: int = 0  # 评论量（原 reply）
    num_like: int = 0  # 点赞量（原 like）
    num_coin: int = 0  # 投币量（原 coin）
    num_fav: int = 0  # 收藏量（原 fav）
    num_share: int = 0  # 转发量（原 share）

    @classmethod
    def from_dict(cls, data: dict) -> "VideoStat":
        """从 view 接口 stat 字段构造。"""
        return cls(
            num_view=data.get("view", 0),
            num_dm=data.get("danmaku", 0),
            num_reply=data.get("reply", 0),
            num_like=data.get("like", 0),
            num_coin=data.get("coin", 0),
            num_fav=data.get("favorite", 0),
            num_share=data.get("share", 0),
        )


@dataclass
class VideoOwner:
    """视频作者（UP主）信息。"""

    mid: int = 0
    name: str = ""  # up主昵称（原 up）
    face: str = ""  # 头像地址
    is_followed: Optional[bool] = None  # 是否已关注该up主（原 up_follow，0/1 -> bool）
    num_followers: Optional[int] = None  # 粉丝数（原 up_followers）

    @classmethod
    def from_view_dict(cls, data: dict) -> "VideoOwner":
        """从 view 接口 owner 字段构造。"""
        return cls(
            mid=data.get("mid", 0),
            name=data.get("name", ""),
            face=data.get("face", ""),
        )


@dataclass
class VideoUserAction:
    """观众对该视频的互动状态（点赞/投币/收藏）。"""

    num_like: int = 0  # 是否点赞 0,1（原 user_like）
    num_coin: int = 0  # 投币数量 0,1,2（原 user_coin）
    num_fav: int = 0  # 是否收藏 0,1（原 user_fav）


@dataclass
class VideoPage:
    """分P视频的单个分P（view 接口 pages 数组的一项）。"""

    page: int = 1  # 分P序号，从1开始
    cid: int = 0  # 该P的cid（playurl 鉴权参数）
    part: str = ""  # 该P的标题（part 字段）
    duration: int = 0  # 该P时长（秒）
    width: int = 0  # 分辨率宽
    height: int = 0  # 分辨率高

    @classmethod
    def from_dict(cls, data: dict) -> "VideoPage":
        dim = data.get("dimension") or {}
        return cls(
            page=data.get("page", 1),
            cid=data.get("cid", 0),
            part=data.get("part", ""),
            duration=data.get("duration", 0),
            width=dim.get("width", 0),
            height=dim.get("height", 0),
        )


@dataclass
class VideoSeason:
    """视频所属的合集（ugc_season）信息。"""

    id: int = 0  # season_id
    title: str = ""  # 合集标题
    mid: int = 0  # 合集创建者UID
    ep_count: int = 0  # 合集内稿件数
    episodes: list = field(default_factory=list)  # 合集内全部稿件（VideoSeasonEpisode 列表）

    @classmethod
    def from_dict(cls, data: dict) -> "VideoSeason":
        episodes = []
        for section in data.get("sections") or []:
            for ep in section.get("episodes") or []:
                ep_bvid = ep.get("bvid") or ""
                ep_aid = ep.get("aid") or 0
                pages = [VideoPage.from_dict(p) for p in (ep.get("pages") or [])]
                first_cid = pages[0].cid if pages else 0
                episodes.append(VideoSeasonEpisode(
                    bvid=ep_bvid,
                    aid=ep_aid,
                    cid=first_cid,
                    title=ep.get("title", ""),
                    section=section.get("title", ""),
                    pages=pages,
                ))
        return cls(
            id=data.get("id", 0),
            title=data.get("title", ""),
            mid=data.get("mid", 0),
            ep_count=data.get("ep_count", 0),
            episodes=episodes,
        )


@dataclass
class VideoSeasonEpisode:
    """合集内的单个稿件（一个视频，可能含多P）。"""

    bvid: str = ""
    aid: int = 0
    cid: int = 0  # 首个分P的cid
    title: str = ""  # 稿件标题
    section: str = ""  # 所在分区（如「正片」）
    pages: list = field(default_factory=list)  # 该稿件分P（VideoPage 列表）

    @property
    def is_multi_page(self) -> bool:
        return len(self.pages) > 1


@dataclass
class VideoInfo:
    """视频信息（旧 BiliVideo 重构后的数据主体）。

    对于多P视频，`pages` 保存全部分P；`cid` 为首个分P的 cid（兼容单P场景）。
    """

    bvid: str = ""
    aid: int = 0
    cid: Optional[int] = None  # 分P cid（鉴权参数，默认取第一个分P）

    title: str = ""  # 视频标题
    pic: str = ""  # 封面地址
    desc: str = ""  # 简介
    pub_time: int = 0  # 稿件发布时间 pubdate（原 time）

    tid: int = 0  # 分区tid
    tname: str = ""  # 子分区名称

    tags: list = field(default_factory=list)  # 视频标签（tag_name 列表）

    stat: VideoStat = field(default_factory=VideoStat)  # 统计数据
    owner: Optional[VideoOwner] = None  # 作者信息
    user_action: Optional[VideoUserAction] = None  # 观众互动状态（需要时另行获取）

    pages: list = field(default_factory=list)  # 全部分P（VideoPage 列表，多P视频有多个）
    season: Optional[VideoSeason] = None  # 所属合集（ugc_season），不属于合集时为 None

    dash: Optional[DashStreams] = None  # DASH 下载流信息（请求 playurl 后填充）

    @property
    def is_multi_page(self) -> bool:
        """是否为多P视频。"""
        return len(self.pages) > 1

    @classmethod
    def from_view_json(cls, data: dict) -> "VideoInfo":
        """从视频信息接口（x/web-interface/view）的 data 字段构造。

        :param data: view 接口返回的 data 字典
        :return: VideoInfo（cid 取第一个分P；pages 保存全部分P；season 保存所属合集）
        """
        pages = data.get("pages") or []
        first_page = pages[0] if pages else {}
        owner_data = data.get("owner") or {}
        season_data = data.get("ugc_season")
        return cls(
            bvid=data.get("bvid", ""),
            aid=data.get("aid", 0),
            cid=first_page.get("cid") if first_page else None,
            title=data.get("title", ""),
            pic=data.get("pic", ""),
            desc=data.get("desc", ""),
            pub_time=data.get("pubdate", 0),
            tid=data.get("tid", 0),
            tname=data.get("tname", ""),
            stat=VideoStat.from_dict(data.get("stat") or {}),
            owner=VideoOwner.from_view_dict(owner_data),
            pages=[VideoPage.from_dict(p) for p in pages],
            season=VideoSeason.from_dict(season_data) if season_data else None,
        )
