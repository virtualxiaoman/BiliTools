"""直播消息解析（纯函数，不做网络请求与文件 IO）。

[分层] ``src/services/live.py``（LiveService：网络/长连接/落盘编排）
        → 本模块（二进制包与 JSON 消息 → 数据模型）
        → ``src/models/live_model.py``

[协议要点]（2026-10-03 实测于真实直播间）
- WebSocket 二进制帧载荷 = 若干个「16 字节头 + 正文」的包：
  总长(4) / 头长(2) / protover(2) / op(4) / seq(4)；
- op: 2 心跳 / 3 心跳回复（前 4 字节 uint32 人气值）/ 5 业务消息 / 7 认证 / 8 认证回复；
- protover=2 的 op=5 正文为 zlib 压缩（标准库解压），内部是若干 protover=0 的普通包；
  以 protover=2 认证时服务端不会下发 brotli(3)，无需额外依赖；
- DANMU_MSG 的 ``info`` 是位置数组（下标含义见 ``parse_danmaku`` 注释），
  实测 info 长度 18，字段缺失时按位置逐个降级。
"""

import json
import struct
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.models.live_model import DanmakuMessage, RoomInfo, format_time

# WS 包操作码
WS_OP_HEARTBEAT = 2
WS_OP_HEARTBEAT_REPLY = 3
WS_OP_MESSAGE = 5
WS_OP_AUTH = 7
WS_OP_AUTH_REPLY = 8

# 认证时使用的协议版本：2 = zlib（标准库可解），3 = brotli（需要第三方库，不使用）
WS_PROTOVER = 2

# 生成用包头
_HEADER = struct.Struct(">IHHII")

_BEIJING = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class WsPacket:
    """一个解码后的 WS 业务包。"""

    protover: int
    op: int
    body: bytes


def build_packet(op: int, body: bytes = b"", protover: int = 1) -> bytes:
    """构造发往弹幕服务器的包（认证包 protover=1，心跳包为空正文）。"""
    return _HEADER.pack(_HEADER.size + len(body), _HEADER.size, protover, op, 1) + body


def build_auth_payload(room_id: int, uid: int, token: str, *, buvid: str = "") -> bytes:
    """构造认证 JSON（op=7）。

    实测（2026-10-03）：``uid=0`` 匿名认证会被服务端静默断开，必须使用登录态 mid；
    ``buvid`` 为可选项（getDanmuInfo 响应会顺带在会话 cookie 里种上 buvid3）。
    """
    payload = {
        "uid": int(uid),
        "roomid": int(room_id),
        "protover": WS_PROTOVER,
        "platform": "web",
        "type": 2,
        "key": token,
    }
    if buvid:
        payload["buvid"] = buvid
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def parse_ws_payload(payload: bytes) -> list[WsPacket]:
    """解析一帧 WS 载荷 → 业务包列表（自动解压 protover=2 的复合包）。

    尾部不完整的包直接忽略（正常不会出现；出现说明流已错位，由调用方重连兜底）。
    """
    packets: list[WsPacket] = []
    for protover, op, body in _split_packets(payload):
        if op == WS_OP_MESSAGE and protover == 2:
            try:
                inner = zlib.decompress(body)
            except zlib.error as exc:
                raise ValueError(f"zlib 解压失败：{exc}") from exc
            packets.extend(parse_ws_payload(inner))
        elif protover == 3:
            raise ValueError("收到 brotli 压缩包（protover=3）：本项目以 protover=2 认证，不应出现")
        else:
            packets.append(WsPacket(protover=protover, op=op, body=body))
    return packets


def _split_packets(payload: bytes) -> list[tuple[int, int, bytes]]:
    out: list[tuple[int, int, bytes]] = []
    offset = 0
    while offset + _HEADER.size <= len(payload):
        total, head_size, protover, op, _seq = _HEADER.unpack_from(payload, offset)
        if head_size < _HEADER.size or total < head_size or offset + total > len(payload):
            break
        out.append((protover, op, payload[offset + head_size:offset + total]))
        offset += total
    return out


def parse_auth_reply(body: bytes) -> dict:
    """解析认证回复（op=8）的 JSON。"""
    if not body:
        return {}
    try:
        data = json.loads(body)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def parse_heartbeat_reply(body: bytes) -> int:
    """解析心跳回复（op=3）前 4 字节的人气值。"""
    if len(body) < 4:
        return 0
    return struct.unpack(">I", body[:4])[0]


def is_danmaku_cmd(cmd: str) -> bool:
    """是否为弹幕消息（含 ``DANMU_MSG:4:0:2:2:2:0`` 之类的变体后缀）。"""
    return cmd == "DANMU_MSG" or cmd.startswith("DANMU_MSG:")


# ---- 数据解析 ----

def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _at(seq, index: int, default=None):
    """按位置安全取值（位置数组字段缺失/越界时返回 default）。"""
    try:
        return seq[index]
    except (IndexError, KeyError, TypeError):
        return default


def parse_room_info(data: dict) -> RoomInfo:
    """room/v1/Room/get_info 的 data → RoomInfo。"""
    data = data if isinstance(data, dict) else {}
    return RoomInfo(
        room_id=_to_int(data.get("room_id")),
        short_id=_to_int(data.get("short_id")),
        uid=_to_int(data.get("uid")),
        live_status=_to_int(data.get("live_status")),
        title=str(data.get("title") or ""),
        area_name=str(data.get("area_name") or ""),
        online=_to_int(data.get("online")),
        attention=_to_int(data.get("attention")),
        live_time=str(data.get("live_time") or ""),
        cover=str(data.get("user_cover") or ""),
    )


def parse_danmaku(msg: dict) -> Optional[DanmakuMessage]:
    """DANMU_MSG → DanmakuMessage；结构不合法（既无文本也无表情）时返回 None。

    实测 info 位置数组（2026-10-03）：
    - info[0]: [.., .., 字号, 颜色, 毫秒时间戳, .., ..., {extra: ...}]
    - info[1]: 弹幕文本
    - info[2]: [uid, 用户名, 房管标识, ...]
    - info[3]: [勋章等级, 勋章名, UP 名, 房间号, ...]
    - info[4]: [用户等级, ...]
    - info[7]: 大航海等级（0 无 / 1 总督 / 2 提督 / 3 舰长）
    - info[9]: {"ts": 秒级时间戳, ...}
    - info[13]: 表情 {url, ...} 或 None
    """
    info = msg.get("info")
    if not isinstance(info, list):
        return None

    text = str(_at(info, 1, "") or "")
    sender = _at(info, 2) or []
    uid = _to_int(_at(sender, 0))
    uname = str(_at(sender, 1, "") or "")
    is_admin = _to_int(_at(sender, 2))

    ts = 0.0
    meta = _at(info, 0) or []
    ts_ms = _to_int(_at(meta, 4))
    if ts_ms > 0:
        ts = ts_ms / 1000.0
    if ts <= 0:
        ts_box = _at(info, 9)
        if isinstance(ts_box, dict):
            ts = float(_to_int(ts_box.get("ts")))

    medal = _at(info, 3) or []
    user_level_row = _at(info, 4) or []
    emoticon = _at(info, 13)
    emoticon_url = str(emoticon.get("url") or "") if isinstance(emoticon, dict) else ""

    if not text and not emoticon_url:
        return None
    return DanmakuMessage(
        text=text,
        uid=uid,
        uname=uname,
        ts=ts,
        is_admin=is_admin,
        guard_level=_to_int(_at(info, 7)),
        user_level=_to_int(_at(user_level_row, 0)),
        medal_name=str(_at(medal, 1) or ""),
        medal_level=_to_int(_at(medal, 0)),
        emoticon_url=emoticon_url,
    )


def parse_history_item(item: dict) -> Optional[DanmakuMessage]:
    """gethistory 的 data.room 数组元素 → DanmakuMessage。

    历史接口字段是命名键（text/nickname/timeline/medal/user_level/emoticon 等），
    与 WS 的位置数组不同；时间优先取 check_info.ts，缺失时解析 timeline。
    """
    if not isinstance(item, dict):
        return None
    text = str(item.get("text") or "")
    check = item.get("check_info")
    ts = float(_to_int(check.get("ts"))) if isinstance(check, dict) else 0.0
    if ts <= 0:
        ts = _parse_timeline(item.get("timeline"))

    medal = item.get("medal") or []
    user_level_row = item.get("user_level") or []
    emoticon = item.get("emoticon")
    emoticon_url = str(emoticon.get("url") or "") if isinstance(emoticon, dict) else ""
    if not text and not emoticon_url:
        return None
    return DanmakuMessage(
        text=text,
        uid=_to_int(item.get("uid")),
        uname=str(item.get("nickname") or ""),
        ts=ts,
        is_admin=_to_int(item.get("isadmin")),
        guard_level=_to_int(item.get("guard_level")),
        user_level=_to_int(_at(user_level_row, 0)),
        medal_name=str(_at(medal, 1) or ""),
        medal_level=_to_int(_at(medal, 0)),
        emoticon_url=emoticon_url,
    )


def _parse_timeline(value) -> float:
    """gethistory 的 timeline（"YYYY-MM-DD HH:MM:SS"，北京时间）→ 时间戳；失败返回 0。"""
    if not isinstance(value, str) or not value:
        return 0.0
    try:
        moment = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_BEIJING)
    except ValueError:
        return 0.0
    return moment.timestamp()


def build_record(cmd: str, msg: dict, received_at: float) -> tuple[Optional[dict], Optional[str]]:
    """任意消息 → (落盘记录, TXT 文本行)；无归档价值时返回 (None, None)。

    弹幕（含变体）解析为结构化记录并附纯文本行；其他 cmd 走通用摘要（只有 JSONL 记录）。
    """
    if is_danmaku_cmd(cmd):
        danmaku = parse_danmaku(msg)
        if danmaku is None:
            return None, None
        record = danmaku.to_record()
        record["type"] = cmd  # 保留变体后缀（如 DANMU_MSG:4:0:2:2:2:0）以保真
        return record, danmaku.to_text_line()
    record = summarize_message(cmd, msg, received_at)
    return record, None


# ---- 非弹幕消息：通用摘要 ----

def _pick_ts(data: dict) -> int:
    """从 data 中挑选可信的秒级时间戳字段（无则 0）。"""
    for key in ("ts", "timestamp", "send_time", "time"):
        value = _to_int(data.get(key))
        if value > 10 ** 8:  # 合理的时间戳下限（1973 年起）
            return value
    return 0


def summarize_message(cmd: str, msg: dict, received_at: float) -> Optional[dict]:
    """非弹幕消息 → 通用记录（附带原始 payload 便于后续分析）。

    已知类型提取常用字段；未知类型只保留 type/时间/raw。返回 None 表示该消息无归档价值。
    """
    data = msg.get("data")
    data = data if isinstance(data, dict) else {}
    ts = _pick_ts(data) or int(received_at)
    record = {"type": cmd, "time": format_time(ts), "ts": ts}

    if cmd == "SUPER_CHAT_MESSAGE":
        user = data.get("user_info") if isinstance(data.get("user_info"), dict) else {}
        record.update({
            "text": str(data.get("message") or ""),
            "uid": _to_int(data.get("uid")),
            "uname": str(user.get("uname") or ""),
            "price": _to_int(data.get("price")),
        })
    elif cmd in ("SEND_GIFT", "COMBO_SEND"):
        record.update({
            "uid": _to_int(data.get("uid")),
            "uname": str(data.get("uname") or ""),
            "gift": str(data.get("giftName") or data.get("gift_name") or ""),
            "num": _to_int(data.get("num") or data.get("total_num")),
            "price": _to_int(data.get("price")),
            "total_coin": _to_int(data.get("total_coin")),
        })
    elif cmd == "GUARD_BUY":
        record.update({
            "uid": _to_int(data.get("uid")),
            "uname": str(data.get("username") or ""),
            "gift": str(data.get("gift_name") or ""),
            "num": _to_int(data.get("num")),
            "price": _to_int(data.get("price")),
        })
    elif cmd in ("INTERACT_WORD", "INTERACT_WORD_V2"):
        # V2 的 data 仅含 protobuf（pb 字段），仅保留原始 payload
        record.update({
            "uid": _to_int(data.get("uid")),
            "uname": str(data.get("uname") or ""),
            "msg_type": _to_int(data.get("msg_type")),
        })
    elif cmd == "ENTRY_EFFECT":
        record.update({
            "uid": _to_int(data.get("uid")),
            "text": str(data.get("copy_writing") or ""),
        })
    else:
        record["raw"] = msg
        return record

    record["raw"] = msg
    return record
