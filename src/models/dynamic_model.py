"""动态（opus）相关的数据模型。

解析入口见 `src/services/dynamic.py::DynamicService.parse_item`，
下载入口见 `DynamicService.download_dynamic`。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DynamicAuthor:
    """动态作者信息（含头像/挂件/装扮资源地址）。"""

    mid: int = 0
    name: str = ""
    face: str = ""
    pub_time: str = ""
    pub_ts: int = 0
    location: str = ""
    pendant_name: str = ""
    pendant_image: str = ""  # 静态挂件图
    pendant_image_enhance: str = ""  # 动态挂件（优先下载）
    decorate_name: str = ""
    decorate_card: str = ""  # 装扮卡（粉丝卡片背景）


@dataclass
class DynamicTopic:
    """动态话题。"""

    id: int = 0
    name: str = ""
    jump_url: str = ""


@dataclass
class DynamicImage:
    """正文图片（含 live photo 信息与落盘文件名）。"""

    index: int = 0
    url: str = ""
    width: int = 0
    height: int = 0
    size_kb: float = 0.0
    live_url: str = ""  # 非空表示动态图（live photo），视频资源
    aigc: int = 0
    file: str = ""  # 相对动态目录的落盘路径，下载后回填
    live_file: str = ""  # 动态图视频的落盘路径（相对动态目录），下载后回填


@dataclass
class DynamicEmoji:
    """正文内联表情（引用表情包素材）。"""

    text: str = ""
    package_id: str = ""
    emoji_id: str = ""
    url: str = ""  # gif 优先，回退 webp / icon
    short_name: str = ""
    file: str = ""  # 相对动态目录的落盘路径，下载后回填


@dataclass
class DynamicCard:
    """各类附加卡片（视频/商品/预约/直播等）的元数据。"""

    kind: str = ""  # archive / goods / common / reserve / live / pgc / ...
    title: str = ""
    desc: str = ""
    jump_url: str = ""
    cover_url: str = ""  # 主封面（多封面卡片见 extra）
    cover_file: str = ""  # 相对动态目录的落盘路径
    bvid: str = ""
    extra: dict = field(default_factory=dict)  # 该卡片原始字段（含 items 等）


@dataclass
class DynamicStats:
    """动态统计（点赞/评论/转发计数）。"""

    like: int = 0
    comment: int = 0
    forward: int = 0


@dataclass
class DynamicContent:
    """动态正文：纯文本 + 结构化块。"""

    title: str = ""
    text: str = ""
    blocks: list = field(default_factory=list)  # 见 parse_item 的 blocks 契约
    truncated: bool = False  # summary.has_more（长文被截断）
    full_text_fetched: bool = False  # 是否已用 opus/detail 取回全文


@dataclass
class DynamicForward:
    """转发信息；orig 为递归解析出的原动态。"""

    orig_id: int = 0
    orig_mid: int = 0
    deleted: bool = False
    orig: Optional["DynamicInfo"] = None
    archive_dir: str = ""  # 原动态落盘目录（相对本条动态目录），下载后回填


@dataclass
class DynamicInfo:
    """一条动态的完整解析结果。"""

    id: int = 0
    type: str = ""  # 原始 DYNAMIC_TYPE_*
    kind: str = "unknown"  # 归一化类型：word/draw/forward/archive/article/...
    url: str = ""
    author: DynamicAuthor = field(default_factory=DynamicAuthor)
    topic: Optional[DynamicTopic] = None
    content: DynamicContent = field(default_factory=DynamicContent)
    images: list = field(default_factory=list)  # list[DynamicImage]
    emojis: list = field(default_factory=list)  # list[DynamicEmoji]
    cards: list = field(default_factory=list)  # list[DynamicCard]
    lottery_rid: str = ""
    vote: Optional[dict] = None  # additional.vote 原始数据（选项等）
    additional: dict = field(default_factory=dict)  # 原始 additional（投票/抽奖等）
    stats: DynamicStats = field(default_factory=DynamicStats)
    forward: Optional[DynamicForward] = None
    comment_oid: int = 0
    comment_type: int = 0
    raw: dict = field(default_factory=dict, repr=False)  # 原始 item


@dataclass
class DynamicDownloadResult:
    """一次动态下载的结果汇总。"""

    path: Path  # 动态目录
    md_path: Optional[Path] = None
    cached: bool = False
    media: list = field(default_factory=list)  # list[DownloadResult]
    comments_path: Optional[Path] = None
    forwarded: list = field(default_factory=list)  # list[DynamicDownloadResult]
    failures: list = field(default_factory=list)  # 失败资源描述
    warnings: list = field(default_factory=list)
