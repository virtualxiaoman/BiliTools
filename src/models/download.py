"""
下载相关的数据模型：清晰度枚举、下载结果、DASH 流数据。

M2 引入：`VideoQuality` 枚举替代旧代码的 qn/fnval 魔法数；
`DownloadResult` 作为下载接口的统一返回值（替代旧代码的 True/False）。
"""

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Optional


class VideoQuality(IntEnum):
    """视频清晰度（qn 参数）。具体值对应 BAC 文档清晰度定义。

    注意：DASH 格式下 qn 不决定返回哪一档，而是返回全部可用流，
    由调用方按清晰度从高到低挑选（见 DashStreams.pick_video）。

    参考：https://socialsisteryi.github.io/bilibili-API-collect/docs/video/videostream_url.html
    """

    P360 = 16  # 360P 流畅
    P480 = 32  # 480P 清晰
    P720 = 64  # 720P 高清
    P720_60 = 74  # 720P60 高帧率
    P1080 = 80  # 1080P 高清
    P1080_PLUS = 112  # 1080P+ 高码率（大会员）
    P1080_60 = 116  # 1080P60 高帧率
    HD4K = 120  # 4K 超清（需 fourk=1，大会员）
    HDR = 125  # HDR 真彩色（需 fnval&64=64）
    DOLBY = 126  # 杜比视界（需 fnval&512=512）
    HD8K = 127  # 8K 超高清

    @property
    def display_name(self) -> str:
        """清晰度的展示名称（如 `4K`、`1080P`），用于进度条等。"""
        return {
            self.P360: "360P",
            self.P480: "480P",
            self.P720: "720P",
            self.P720_60: "720P60",
            self.P1080: "1080P",
            self.P1080_PLUS: "1080P+",
            self.P1080_60: "1080P60",
            self.HD4K: "4K",
            self.HDR: "HDR",
            self.DOLBY: "杜比",
            self.HD8K: "8K",
        }[self]

    @classmethod
    def from_qn(cls, qn: int) -> Optional["VideoQuality"]:
        """将 playurl 流里的 qn(id) 值映射回清晰度枚举；未知值返回 None。

        实际挑选出的流清晰度可能低于请求值（回退），用于进度条显示真实清晰度。
        """
        try:
            return cls(qn)
        except ValueError:
            return None


@dataclass
class DownloadResult:
    """下载结果：文件最终保存的位置与类型。"""

    path: Path  # 文件完整路径
    media_type: str = "video"  # video / audio / cover / videoshot
    size: Optional[int] = None  # 文件字节数（下载完成后回填）

    def __str__(self) -> str:
        return f"DownloadResult(path={self.path}, media_type={self.media_type})"


@dataclass
class VideoStream:
    """DASH 视频流（一个清晰度的视频流）。"""

    url: str  # baseUrl 直链
    codecs: str = ""  # 编码格式（avc1/hev1 等）
    width: int = 0
    height: int = 0
    quality: int = 0  # qn 值，数值越大清晰度越高
    frame_rate: str = ""
    size: int = 0  # 文件大小（字节）

    @property
    def ext(self) -> str:
        """推断扩展名：优先取 URL 后缀，av1/hevc 取 m4s，否则 m4s/mp4。"""
        suffix = Path(self.url).suffix.lower().lstrip(".")
        if suffix in ("mp4", "flv", "m4s"):
            return suffix
        if "av1" in self.codecs or "hev" in self.codecs:
            return "m4s"
        return "m4s"


@dataclass
class AudioStream:
    """DASH 音频流。"""

    url: str  # baseUrl 直链
    codecs: str = ""
    bandwidth: int = 0
    size: int = 0

    @property
    def ext(self) -> str:
        suffix = Path(self.url).suffix.lower().lstrip(".")
        if suffix in ("m4a", "mp3", "flac", "aac", "mp4"):
            return suffix
        return "m4a"


@dataclass
class DashStreams:
    """一次 playurl 请求返回的完整 DASH 流信息。

    构造后自动排序：video 按 quality 降序，audio 按 bandwidth 降序，
    因此 `best_video()` / `best_audio()` 始终返回最高可用流。
    """

    video: list = field(default_factory=list)  # VideoStream 列表
    audio: list = field(default_factory=list)  # AudioStream 列表

    def __post_init__(self) -> None:
        self.video.sort(key=lambda s: s.quality, reverse=True)
        self.audio.sort(key=lambda s: s.bandwidth, reverse=True)

    def best_video(self) -> Optional[VideoStream]:
        """返回清晰度最高的视频流。"""
        return self.video[0] if self.video else None

    def pick_video(self, min_quality: VideoQuality) -> Optional[VideoStream]:
        """按最小清晰度要求挑选视频流：取不低于 min_quality 的最高清晰度流。

        若全部流低于要求，退回清晰度最高的一条。
        """
        if not self.video:
            return None
        for stream in self.video:  # 已按 quality 降序
            if stream.quality >= min_quality:
                return stream
        return self.video[0]

    def best_audio(self) -> Optional[AudioStream]:
        """返回码率最高的音频流。"""
        return self.audio[0] if self.audio else None
