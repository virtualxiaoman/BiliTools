"""LiveService 单元测试（不联网）：用假会话 + 假 WebSocket 驱动监听主流程。"""

import json
import socket
import struct
import types
import zlib

import pytest

from src.api.errors import BiliAuthError
from src.services.live import (
    STOP_DURATION,
    STOP_ERROR,
    STOP_MAX_COUNT,
    STOP_ROOM_END,
    LiveService,
    _accepts,
    _normalize_message_types,
)
from src.services.live_parse import (
    WS_OP_AUTH,
    WS_OP_AUTH_REPLY,
    WS_OP_HEARTBEAT_REPLY,
    WS_OP_MESSAGE,
    build_packet,
)
from src.urls.live_urls import LiveUrls
from src.urls.login_urls import LoginUrls

ROOM_DOC = {
    "room_id": 350353, "short_id": 0, "uid": 11272072, "live_status": 1,
    "title": "画画舰长头像", "area_name": "虚拟日常", "online": 6765, "attention": 100,
    "live_time": "2026-10-03 15:05:40", "user_cover": "https://i0.hdslb.com/cover.jpg",
}


def _danmaku_msg(text="没胃口", cmd="DANMU_MSG"):
    return {
        "cmd": cmd,
        "dm_v2": "",
        "info": [
            [0, 4, 25, 14893055, 1791022769548],
            text,
            [23232945, "丰辰", 1],
            [34, "六捆", "氵六青", 350353],
            [29, 0, 0, ">50000"],
            ["t", "t"], 0, 3, None, {"ts": 1791022769},
        ],
    }


GIFT_MSG = {"cmd": "SEND_GIFT",
            "data": {"uid": 7, "uname": "送礼人", "giftName": "辣条", "num": 3,
                     "price": 100, "timestamp": 1791022770}}


def _stub_wbi(params=None):
    """替身 WBI 签名：在原地附加 wts/w_rid（与真实 get_wbi 行为一致，避免联网取 key）。"""
    if params is not None:
        params["wts"] = 1
        params["w_rid"] = "stub"
    return 1, "stub"


class FakeCookie:
    def __init__(self, bili_jct="csrf-token"):
        self.bili_jct = bili_jct
        self.cookie = "SESSDATA=fake; bili_jct=fake"
        self.has_valid_session = True


class FakeSession:
    """按 URL 分发的假会话：记录调用、返回预置数据。"""

    def __init__(self, responses=None, cookie=None):
        self.responses = responses or {}
        self.cookie = cookie if cookie is not None else FakeCookie()
        self.calls = []
        self.session = types.SimpleNamespace(
            cookies=types.SimpleNamespace(get=lambda name, default=None: "buvid3-fake")
        )

    def get(self, url, params=None, headers=None, **kwargs):
        self.calls.append(("GET", url, dict(params or {}), headers))
        return json.loads(json.dumps(self.responses.get(url, {})))

    def post(self, url, data=None, params=None, headers=None, **kwargs):
        self.calls.append(("POST", url, dict(data or {}), headers))
        return json.loads(json.dumps(self.responses.get(url, {})))


class FakeWebSocket:
    """假 WS：sock 为 socketpair 一端（select 可用），recv 按「4 字节长度 + 载荷」读帧。"""

    def __init__(self, url, **kwargs):
        self.url = url
        self.kwargs = kwargs
        self.sent = []
        self._inbound, self.server_side = socket.socketpair()
        self.sock = self._inbound
        self.closed = False

    def recv(self):
        return self._read_exact(struct.unpack(">I", self._read_exact(4))[0])

    def _read_exact(self, size):
        data = b""
        while len(data) < size:
            chunk = self._inbound.recv(size - len(data))
            if not chunk:
                raise ConnectionError("closed")
            data += chunk
        return data

    def send(self, payload):
        self.sent.append(payload)

    def close(self):
        self.closed = True
        self._inbound.close()
        self.server_side.close()


def _push(server_side, payload: bytes) -> None:
    server_side.sendall(struct.pack(">I", len(payload)) + payload)


def _make_service(tmp_path, responses, monkeypatch, ws=None):
    monkeypatch.setattr("src.services.live.get_wbi", _stub_wbi)
    session = FakeSession(responses)
    created = {"ws": ws, "url": None, "kwargs": {}}

    def factory(url, **kwargs):
        created["url"], created["kwargs"] = url, kwargs
        if created["ws"] is None:
            created["ws"] = FakeWebSocket(url, **kwargs)
        else:
            created["ws"].kwargs = kwargs  # 记录本次连接的实参（预创建场景）
        return created["ws"]

    service = LiveService(session=session, default_dir=tmp_path, ws_factory=factory)
    return service, session, created


def _base_responses():
    return {
        LiveUrls.ROOM_INFO: ROOM_DOC,
        LoginUrls.LOGIN_STATE: {"isLogin": True, "mid": 506925078},
        LiveUrls.DANMU_INFO: {"token": "tok-123", "host_list": [
            {"host": "h1.example", "wss_port": 2245}, {"host": "h2.example", "wss_port": 2245}]},
    }


# ---- 房间信息 / 快照 / 发送 ----

def test_get_room_info_parses_and_requests(monkeypatch):
    service, session, _ = _make_service(None, _base_responses(), monkeypatch)
    info = service.get_room_info(350353)
    assert info.room_id == 350353 and info.living
    method, url, params, _ = session.calls[-1]
    assert (method, url) == ("GET", LiveUrls.ROOM_INFO)
    assert params == {"room_id": 350353}


def test_fetch_recent_danmaku_signs_and_parses(monkeypatch):
    responses = _base_responses()
    responses[LiveUrls.DANMU_HISTORY] = {"room": [
        {"text": "好帅", "uid": 1, "nickname": "aodun1", "timeline": "2024-08-16 22:33:28",
         "check_info": {"ts": 1723818808}},
        {"text": "", "uid": 2, "nickname": "x", "timeline": ""},
    ]}
    service, session, _ = _make_service(None, responses, monkeypatch)
    messages = service.fetch_recent_danmaku(350353)
    assert len(messages) == 1 and messages[0].text == "好帅"
    _, url, params, _ = session.calls[-1]
    assert url == LiveUrls.DANMU_HISTORY
    assert params["roomid"] == 350353 and params["room_type"] == 0
    assert "w_rid" in params and "wts" in params  # WBI 签名参数已附加


def test_send_danmaku_builds_request(monkeypatch):
    service, session, _ = _make_service(None, {LiveUrls.SEND_DANMU: {"mode_info": {}}}, monkeypatch)
    result = service.send_danmaku(25774901, "  你好  ")
    assert result == {"mode_info": {}}
    method, url, data, _ = session.calls[-1]
    assert (method, url) == ("POST", LiveUrls.SEND_DANMU)
    assert data["msg"] == "你好" and data["roomid"] == 25774901
    assert data["csrf"] == "csrf-token" and data["csrf_token"] == "csrf-token"
    assert data["color"] == 16777215 and data["fontsize"] == 25 and data["mode"] == 1
    assert isinstance(data["rnd"], int)


def test_send_danmaku_requires_login(monkeypatch):
    responses = _base_responses()
    session = FakeSession(responses, cookie=FakeCookie(bili_jct=None))
    monkeypatch.setattr("src.services.live.get_wbi", _stub_wbi)
    service = LiveService(session=session)
    with pytest.raises(BiliAuthError):
        service.send_danmaku(1, "hi")


def test_send_danmaku_rejects_empty(monkeypatch):
    service, _, _ = _make_service(None, _base_responses(), monkeypatch)
    with pytest.raises(ValueError):
        service.send_danmaku(1, "   ")


# ---- 监听：停止条件与参数校验 ----

def test_listen_returns_early_when_room_offline(tmp_path, monkeypatch):
    responses = _base_responses()
    responses[LiveUrls.ROOM_INFO] = dict(ROOM_DOC, live_status=0)
    service, _, _ = _make_service(tmp_path, responses, monkeypatch)
    result = service.listen_danmaku(350353, stop_on_room_end=True)
    assert result.stop_reason == STOP_ROOM_END
    assert result.session_dir is None
    assert list(tmp_path.iterdir()) == []  # 未落盘


def test_listen_requires_login(tmp_path, monkeypatch):
    responses = _base_responses()
    responses[LoginUrls.LOGIN_STATE] = {"isLogin": False, "mid": None}
    service, _, _ = _make_service(tmp_path, responses, monkeypatch)
    with pytest.raises(BiliAuthError):
        service.listen_danmaku(350353, duration=1)


def test_listen_rejects_bad_args(tmp_path, monkeypatch):
    service, _, _ = _make_service(tmp_path, _base_responses(), monkeypatch)
    with pytest.raises(ValueError):
        service.listen_danmaku(350353, duration=0)
    with pytest.raises(ValueError):
        service.listen_danmaku(350353, max_count=-1)


# ---- 监听：主流程 ----

def test_listen_records_danmaku_and_filters_others(tmp_path, monkeypatch, capsys):
    service, session, created = _make_service(tmp_path, _base_responses(), monkeypatch)
    ws = created["ws"] = FakeWebSocket("wss://h1.example:2245/sub")
    _push(ws.server_side, build_packet(WS_OP_AUTH_REPLY, b'{"code":0}'))
    _push(ws.server_side, build_packet(WS_OP_MESSAGE, json.dumps(GIFT_MSG).encode()))  # 默认被过滤
    variant = _danmaku_msg(text="变体弹幕", cmd="DANMU_MSG:4:0:2:2:2:0")
    inner = build_packet(WS_OP_MESSAGE, json.dumps(variant).encode())
    _push(ws.server_side, build_packet(WS_OP_MESSAGE, zlib.compress(inner), protover=2))
    _push(ws.server_side, build_packet(WS_OP_HEARTBEAT_REPLY, struct.pack(">I", 4321)))

    records = []
    result = service.listen_danmaku(350353, max_count=1, print_messages=True, on_message=records.append)

    assert result.stop_reason == STOP_MAX_COUNT
    assert result.saved == 1
    assert result.counts == {"DANMU_MSG:4:0:2:2:2:0": 1}  # 礼物未计入
    assert records[0]["text"] == "变体弹幕"

    # 落盘三件套
    assert result.session_dir is not None and result.session_dir.parent.name == "350353"
    jsonl = [json.loads(line) for line in result.jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert len(jsonl) == 1 and jsonl[0]["type"] == "DANMU_MSG:4:0:2:2:2:0"
    assert jsonl[0]["text"] == "变体弹幕" and jsonl[0]["medal_name"] == "六捆"
    txt = result.txt_path.read_text(encoding="utf-8").strip()
    assert txt.endswith("丰辰: 变体弹幕")
    meta = json.loads(result.meta_path.read_text(encoding="utf-8"))
    assert meta["room"]["room_id"] == 350353 and meta["account_uid"] == 506925078
    assert meta["status"] == STOP_MAX_COUNT and meta["saved"] == 1

    # 认证包：uid=登录 mid、roomid=真实房间号、protover=2、platform=web、key=token
    auth_body = ws.sent[0][16:]
    auth = json.loads(auth_body)
    assert auth["uid"] == 506925078 and auth["roomid"] == 350353
    assert auth["protover"] == 2 and auth["platform"] == "web" and auth["key"] == "tok-123"
    assert struct.unpack(">IHHII", ws.sent[0][:16])[3] == WS_OP_AUTH
    assert ws.kwargs["origin"] == "https://live.bilibili.com/"
    assert ws.kwargs["timeout"] == 10.0

    # 控制台打印（弹幕行）
    assert "丰辰: 变体弹幕" in capsys.readouterr().out


def test_listen_all_types_captures_gift(tmp_path, monkeypatch):
    service, _, created = _make_service(tmp_path, _base_responses(), monkeypatch)
    ws = created["ws"] = FakeWebSocket("wss://h1.example:2245/sub")
    _push(ws.server_side, build_packet(WS_OP_AUTH_REPLY, b'{"code":0}'))
    _push(ws.server_side, build_packet(WS_OP_MESSAGE, json.dumps(GIFT_MSG).encode()))

    result = service.listen_danmaku(350353, message_types="all", max_count=1)

    assert result.stop_reason == STOP_MAX_COUNT
    assert result.counts == {"SEND_GIFT": 1}
    record = json.loads(result.jsonl_path.read_text(encoding="utf-8").strip())
    assert record["type"] == "SEND_GIFT" and record["gift"] == "辣条"
    assert record["raw"]["data"]["num"] == 3
    # TXT 只写弹幕：礼物不落 TXT
    assert result.txt_path.read_text(encoding="utf-8") == ""


def test_listen_duration_stop_with_silent_room(tmp_path, monkeypatch):
    """静默房间：到点停止；心跳按间隔发送；会话正常收尾（meta 落盘、连接关闭）。"""
    service, _, created = _make_service(tmp_path, _base_responses(), monkeypatch)
    ws = created["ws"] = FakeWebSocket("wss://h1.example:2245/sub")
    _push(ws.server_side, build_packet(WS_OP_AUTH_REPLY, b'{"code":0}'))
    monkeypatch.setattr("src.services.live._HEARTBEAT_INTERVAL", 0.3)

    result = service.listen_danmaku(350353, duration=1.2)

    assert result.stop_reason == STOP_DURATION
    assert result.saved == 0
    assert result.meta_path.exists()
    # 认证包 + 至少一次心跳（op=2）
    ops = [struct.unpack(">IHHII", packet[:16])[3] for packet in ws.sent]
    assert ops[0] == WS_OP_AUTH and 2 in ops
    assert ws.closed


def test_listen_save_false_writes_nothing(tmp_path, monkeypatch):
    """save=False：不落盘，但回调与打印仍然工作。"""
    service, _, created = _make_service(tmp_path, _base_responses(), monkeypatch)
    ws = created["ws"] = FakeWebSocket("wss://h1.example:2245/sub")
    _push(ws.server_side, build_packet(WS_OP_AUTH_REPLY, b'{"code":0}'))
    _push(ws.server_side, build_packet(WS_OP_MESSAGE, json.dumps(_danmaku_msg()).encode()))

    records = []
    result = service.listen_danmaku(350353, max_count=1, save=False, on_message=records.append)

    assert result.stop_reason == STOP_MAX_COUNT and result.saved == 1
    assert result.session_dir is None and result.jsonl_path is None
    assert records[0]["text"] == "没胃口"
    assert list(tmp_path.iterdir()) == []


def test_listen_rotates_host_when_auth_fails(tmp_path, monkeypatch):
    """第一个 host 认证失败 → 换第二个 host 成功。"""
    service, _, _ = _make_service(tmp_path, _base_responses(), monkeypatch)
    attempts = []

    class FailingThenOk:
        def __init__(self, url, **kwargs):
            attempts.append(url)
            self._inner = FakeWebSocket(url, **kwargs)
            code = b'{"code":-101}' if len(attempts) == 1 else b'{"code":0}'
            _push(self._inner.server_side, build_packet(WS_OP_AUTH_REPLY, code))
            self.sock = self._inner.sock

        def recv(self):
            return self._inner.recv()

        def send(self, payload):
            self._inner.send(payload)

        def close(self):
            self._inner.close()

    service._ws_factory = FailingThenOk
    result = service.listen_danmaku(350353, duration=1.0)

    assert attempts == ["wss://h1.example:2245/sub", "wss://h2.example:2245/sub"]
    assert result.stop_reason == STOP_DURATION


def test_listen_stops_after_reconnect_failures(tmp_path, monkeypatch):
    """所有 host 认证失败且不再重试（max_reconnects=0）→ STOP_ERROR 并记录错误。"""
    service, _, _ = _make_service(tmp_path, _base_responses(), monkeypatch)

    class AlwaysFail:
        def __init__(self, url, **kwargs):
            self._inner = FakeWebSocket(url, **kwargs)
            _push(self._inner.server_side, build_packet(WS_OP_AUTH_REPLY, b'{"code":-101}'))
            self.sock = self._inner.sock

        def recv(self):
            return self._inner.recv()

        def send(self, payload):
            self._inner.send(payload)

        def close(self):
            self._inner.close()

    service._ws_factory = AlwaysFail
    result = service.listen_danmaku(350353, max_reconnects=0)

    assert result.stop_reason == STOP_ERROR
    assert result.reconnects == 1
    assert result.errors and "弹幕认证失败" in result.errors[0]


# ---- 过滤规则 ----

def test_message_type_filter_rules():
    default = _normalize_message_types(None)
    assert _accepts("DANMU_MSG", default) and _accepts("DANMU_MSG:4:0:2:2:2:0", default)
    assert not _accepts("SEND_GIFT", default)

    every = _normalize_message_types("all")
    assert every is None
    assert _accepts("SEND_GIFT", every) and _accepts("SUPER_CHAT_MESSAGE", every)
    assert not _accepts("STOP_LIVE_ROOM_LIST", every)

    explicit = _normalize_message_types(["SEND_GIFT", "GUARD_BUY"])
    assert _accepts("SEND_GIFT", explicit) and not _accepts("DANMU_MSG", explicit)

    with pytest.raises(ValueError):
        _normalize_message_types([])
