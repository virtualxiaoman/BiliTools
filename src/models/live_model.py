"""直播（live）相关的数据模型。

[工作流位置]
- 解析输出：``src/services/live_parse.py``（纯解析）产出 ``RoomInfo`` / ``DanmakuMessage``；
- 编排消费：``src/services/live.py``（LiveService）负责网络、长连接与落盘，
  监听结束返回 ``LiveSessionResult``；
- 落盘格式：JSONL 每行一条 ``DanmakuMessage.to_record()``；TXT 用 ``to_text_line()``。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# 北京时间（直播弹幕时间统一按此口径渲染）
_BEIJING = timezone(timedelta(hours=8))


def format_time(ts: float, with_date: bool = False) -> str:
    """时间戳（秒）→ 北京时间文本；ts 无效时返回空串。"""
    try:
        moment = datetime.fromtimestamp(float(ts), _BEIJING)
    except (TypeError, ValueError, OSError, OverflowError):
        return ""
    return moment.strftime("%Y-%m-%d %H:%M:%S" if with_date else "%H:%M:%S")


@dataclass
class RoomInfo:
    """直播间基本信息（room/v1/Room/get_info）。"""

    room_id: int = 0  # 真实房间号（WS 认证必须用真实房间号）
    short_id: int = 0  # 短号，0 表示无短号
    uid: int = 0  # 主播 mid
    live_status: int = 0  # 0 未开播 / 1 直播中 / 2 轮播
    title: str = ""
    area_name: str = ""
    online: int = 0  # 在线人数（人气值）
    attention: int = 0  # 关注数
    live_time: str = ""  # "YYYY-MM-DD HH:MM:SS"，未开播时为 "0000-00-00 00:00:00"
    cover: str = ""

    @property
    def living(self) -> bool:
        return self.live_status == 1


@dataclass
class DanmakuMessage:
    """一条直播弹幕（来源：WebSocket 实时流或 gethistory 历史弹幕）。"""

    text: str = ""
    uid: int = 0
    uname: str = ""
    ts: float = 0.0  # 发送时间（秒级时间戳）
    is_admin: int = 0  # 房管标识
    guard_level: int = 0  # 大航海：0 无 / 1 总督 / 2 提督 / 3 舰长
    user_level: int = 0  # 用户等级
    medal_name: str = ""  # 粉丝勋章名
    medal_level: int = 0  # 粉丝勋章等级
    emoticon_url: str = ""  # 表情弹幕图片地址，非空表示纯表情/含表情

    @property
    def time_text(self) -> str:
        return format_time(self.ts)

    def to_record(self) -> dict:
        """JSONL 落盘记录（danmaku.jsonl 每行）。"""
        return {
            "type": "DANMU_MSG",
            "time": self.time_text,
            "ts": self.ts,
            "uid": self.uid,
            "uname": self.uname,
            "text": self.text,
            "is_admin": self.is_admin,
            "guard_level": self.guard_level,
            "user_level": self.user_level,
            "medal_name": self.medal_name,
            "medal_level": self.medal_level,
            "emoticon": self.emoticon_url,
        }

    def to_text_line(self) -> str:
        """TXT 落盘行（danmaku.txt 每行），纯表情弹幕以 [表情] 占位。"""
        return f"[{self.time_text}] {self.uname}: {self.text or '[表情]'}"


@dataclass
class LiveSessionResult:
    """一次实时弹幕监听会话的结果（落盘位置与统计信息）。"""

    room_id: int = 0
    session_dir: Optional[Path] = None  # 场次目录（未落盘或未开始则为 None）
    jsonl_path: Optional[Path] = None
    txt_path: Optional[Path] = None
    meta_path: Optional[Path] = None
    started_at: float = 0.0  # 会话开始时间（秒级时间戳）
    ended_at: float = 0.0
    stop_reason: str = ""  # 见 src/services/live.py 的 STOP_* 常量
    counts: dict = field(default_factory=dict)  # 各 cmd 收到条数（含未落盘的类型）
    saved: int = 0  # 通过过滤并落盘/回调的条数
    popularity: int = 0  # 最近一次心跳回复的人气值
    reconnects: int = 0  # 断线重连次数
    errors: list = field(default_factory=list)  # 连接失败等错误摘要（最多保留若干条）

    @property
    def duration(self) -> float:
        return max(0.0, self.ended_at - self.started_at)

    @property
    def total(self) -> int:
        """收到的消息总条数（含未落盘的类型）。"""
        return sum(self.counts.values())
