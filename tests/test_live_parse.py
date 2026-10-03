"""直播解析层单元测试（不联网）：WS 包解码、DANMU_MSG/历史弹幕/房间信息解析。

DANMU_MSG 样本取自 2026-10-03 对真实直播间的抓包（info 长度 18）。
"""

import struct
import zlib
from datetime import datetime, timedelta, timezone

import pytest

from src.services.live_parse import (
    WS_OP_AUTH_REPLY,
    WS_OP_HEARTBEAT_REPLY,
    WS_OP_MESSAGE,
    build_auth_payload,
    build_packet,
    build_record,
    is_danmaku_cmd,
    parse_auth_reply,
    parse_danmaku,
    parse_heartbeat_reply,
    parse_history_item,
    parse_room_info,
    parse_ws_payload,
    summarize_message,
)

_BEIJING = timezone(timedelta(hours=8))


def _danmaku_msg(text="没胃口", uid=23232945, uname="丰辰", cmd="DANMU_MSG", emoticon=None):
    """真实抓包样本的 info 数组（字段位置与线上一致）。"""
    return {
        "cmd": cmd,
        "dm_v2": "",
        "info": [
            [0, 4, 25, 14893055, 1791022769548, 1239067740, 0, "087389b7", 0, 0, 0, "", 0, "{}", "{}",
             {"extra": "{}"}],
            text,
            [uid, uname, 1, 0, 0, 10000, 1, "#00D1F1"],
            [34, "六捆", "氵六青", 350353, 7996451, "", 0, 6809855, 7996451, 15304379, 3, 1, 11272072],
            [29, 0, 5805790, ">50000", 0],
            ["title-58-1", "title-58-1"],
            0, 3, None, {"ct": "E7F96D11", "ts": 1791022769}, 0, 0, None, emoticon, 0, 884, [31], None,
        ],
    }


# ---- WS 二进制包 ----

def test_build_packet_layout():
    packet = build_packet(WS_OP_MESSAGE, b"hello")
    total, head_size, protover, op, seq = struct.unpack(">IHHII", packet[:16])
    assert (total, head_size, protover, op, seq) == (16 + 5, 16, 1, WS_OP_MESSAGE, 1)
    assert packet[16:] == b"hello"


def test_parse_ws_payload_plain_packet():
    payload = build_packet(WS_OP_AUTH_REPLY, b'{"code":0}')
    packets = parse_ws_payload(payload)
    assert len(packets) == 1
    assert packets[0].op == WS_OP_AUTH_REPLY
    assert parse_auth_reply(packets[0].body) == {"code": 0}


def test_parse_ws_payload_zlib_composite():
    inner = (build_packet(WS_OP_MESSAGE, b'{"cmd":"A"}')
             + build_packet(WS_OP_MESSAGE, b'{"cmd":"B"}'))
    outer = build_packet(WS_OP_MESSAGE, zlib.compress(inner), protover=2)
    packets = parse_ws_payload(outer)
    assert [packet.op for packet in packets] == [WS_OP_MESSAGE, WS_OP_MESSAGE]
    assert packets[0].body == b'{"cmd":"A"}'
    assert packets[1].body == b'{"cmd":"B"}'


def test_parse_ws_payload_rejects_brotli():
    outer = build_packet(WS_OP_MESSAGE, b"\x00\x01", protover=3)
    with pytest.raises(ValueError, match="brotli"):
        parse_ws_payload(outer)


def test_parse_ws_payload_ignores_partial_tail():
    payload = build_packet(WS_OP_MESSAGE, b"ok") + b"\x00\x01"  # 尾部残包
    packets = parse_ws_payload(payload)
    assert len(packets) == 1 and packets[0].body == b"ok"


def test_parse_heartbeat_reply_popularity():
    assert parse_heartbeat_reply(struct.pack(">I", 12345) + b"echo") == 12345
    assert parse_heartbeat_reply(b"") == 0


def test_build_auth_payload_fields():
    payload = build_auth_payload(350353, 506925078, "tok", buvid="buvid3-x")
    import json
    doc = json.loads(payload)
    assert doc == {
        "uid": 506925078, "roomid": 350353, "protover": 2,
        "platform": "web", "type": 2, "key": "tok", "buvid": "buvid3-x",
    }
    assert b"buvid" not in build_auth_payload(1, 2, "t")


def test_is_danmaku_cmd_matches_variants():
    assert is_danmaku_cmd("DANMU_MSG")
    assert is_danmaku_cmd("DANMU_MSG:4:0:2:2:2:0")
    assert not is_danmaku_cmd("DANMU_MSGX")


# ---- 弹幕解析 ----

def test_parse_danmaku_real_sample():
    message = parse_danmaku(_danmaku_msg())
    assert message is not None
    assert message.text == "没胃口"
    assert (message.uid, message.uname, message.is_admin) == (23232945, "丰辰", 1)
    assert message.guard_level == 3
    assert message.user_level == 29
    assert (message.medal_name, message.medal_level) == ("六捆", 34)
    assert message.ts == pytest.approx(1791022769.548)
    assert message.time_text == "18:19:29"  # 北京时间


def test_parse_danmaku_emoticon_only():
    raw = _danmaku_msg(text="", emoticon={"url": "https://i0.hdslb.com/emo.png", "is_dynamic": 0})
    message = parse_danmaku(raw)
    assert message is not None
    assert message.emoticon_url == "https://i0.hdslb.com/emo.png"
    assert message.to_text_line().endswith(": [表情]")


def test_parse_danmaku_invalid_returns_none():
    assert parse_danmaku({}) is None
    assert parse_danmaku({"info": "bad"}) is None
    empty = _danmaku_msg(text="")
    assert parse_danmaku(empty) is None


def test_parse_danmaku_falls_back_to_info9_ts():
    raw = _danmaku_msg()
    raw["info"][0][4] = 0  # 毫秒时间戳缺失 → 回退 info[9].ts
    message = parse_danmaku(raw)
    assert message is not None and message.ts == 1791022769.0


def test_danmaku_to_record_keys():
    record = parse_danmaku(_danmaku_msg()).to_record()
    assert record["type"] == "DANMU_MSG"
    assert record["text"] == "没胃口" and record["uid"] == 23232945
    assert record["medal_name"] == "六捆" and record["medal_level"] == 34
    assert record["guard_level"] == 3 and record["emoticon"] == ""


# ---- 历史弹幕与房间信息 ----

def test_parse_history_item_uses_check_info_ts():
    item = {
        "text": "好帅", "uid": 3546708493469870, "nickname": "aodun1",
        "timeline": "2024-08-16 22:33:28", "isadmin": 0, "guard_level": 0,
        "medal": [], "user_level": [0, 0, 9868950, ">50000"],
        "check_info": {"ts": 1723818808, "ct": "1B75FB"},
    }
    message = parse_history_item(item)
    assert message is not None
    assert (message.text, message.uname, message.uid) == ("好帅", "aodun1", 3546708493469870)
    assert message.ts == 1723818808.0


def test_parse_history_item_timeline_fallback():
    item = {"text": "hi", "uid": 1, "nickname": "u", "timeline": "2024-08-16 22:33:28"}
    message = parse_history_item(item)
    expected = datetime(2024, 8, 16, 22, 33, 28, tzinfo=_BEIJING).timestamp()
    assert message is not None and message.ts == expected


def test_parse_room_info():
    info = parse_room_info({
        "room_id": 25774901, "short_id": 0, "uid": 506925078, "live_status": 1,
        "title": "测试直播间", "area_name": "虚拟主播", "online": 88, "attention": 1024,
        "live_time": "2026-10-03 15:05:40", "user_cover": "https://i0.hdslb.com/cover.jpg",
    })
    assert info.room_id == 25774901 and info.living is True
    assert info.uid == 506925078 and info.title == "测试直播间"
    assert info.online == 88 and info.cover.endswith("cover.jpg")
    assert parse_room_info({}).living is False


# ---- 通用摘要与记录构建 ----

def test_summarize_gift_extracts_fields():
    record = summarize_message("SEND_GIFT", {
        "cmd": "SEND_GIFT",
        "data": {"uid": 7, "uname": "送礼人", "giftName": "辣条", "num": 3, "price": 100,
                 "timestamp": 1791022770, "total_coin": 300},
    }, received_at=0)
    assert record["type"] == "SEND_GIFT"
    assert record["ts"] == 1791022770
    assert record["gift"] == "辣条" and record["num"] == 3 and record["price"] == 100
    assert record["uid"] == 7 and record["uname"] == "送礼人"


def test_summarize_unknown_keeps_raw():
    record = summarize_message("SOME_NEW_CMD", {"cmd": "SOME_NEW_CMD", "data": {"x": 1}}, received_at=1000)
    assert record["type"] == "SOME_NEW_CMD" and record["ts"] == 1000
    assert record["raw"]["data"] == {"x": 1}


def test_build_record_dispatch():
    record, line = build_record("DANMU_MSG", _danmaku_msg(), received_at=0)
    assert record["type"] == "DANMU_MSG" and line.startswith("[18:19:29] 丰辰: 没胃口")
    record, line = build_record("SEND_GIFT", {"cmd": "SEND_GIFT", "data": {}}, received_at=0)
    assert record["type"] == "SEND_GIFT" and line is None
