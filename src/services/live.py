"""直播服务：房间信息 / 最近弹幕快照 / 实时弹幕监听录制 / 发送弹幕。

[本模块的角色] 直播功能的编排层：负责网络请求、WebSocket 长连接、落盘与统计；
具体解析交给 ``src/services/live_parse.py``（纯函数），数据模型在 ``src/models/live_model.py``。

[实时监听工作流]（2026-10-03 实测要点）
    ① get_room_info（免登录）归一化房间号、取场次元数据；
    ② getDanmuInfo（必须 WBI 签名，否则 -352）→ token + host_list；
    ③ wss 连接 + 认证包 op=7：uid 必须是登录 mid（实测匿名 uid=0 会被服务端静默断开）；
    ④ 循环：op=5 消息按 message_types 过滤解析 → 回调/JSONL/TXT；每 25 秒发 op=2 心跳；
       断线后按 host 列表轮换重连（指数退避），120 秒无任何数据视为连接已死主动重建；
    ⑤ 停止（时长/条数/中断/下播/重连失败）→ 收尾写 meta.json。

[为什么用 protover=2] 服务端只在 protover=3 时下发 brotli 压缩包；protover=2 用 zlib
（标准库即可解压），因此不引入 brotli 依赖。

[落盘] output/live/{room_id}/{YYYY-MM-DD_HHMMSS}/
  - danmaku.jsonl：每行一条记录（type/time/ts/uid/uname/text/勋章/等级…）
  - danmaku.txt  ：弹幕纯文本 ``[HH:MM:SS] 昵称: 内容``（仅弹幕，便于直接阅读）
  - meta.json    ：房间快照、开始/结束时间、条数统计、停止原因、重连次数
"""

import json
import logging
import random
import select
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import websocket

from src.api.auth import get_wbi
from src.api.errors import BiliAuthError, BiliError
from src.api.session import BiliSession
from src.config.constants import UserAgent
from src.config.path import LIVE_OUTPUT_DIR
from src.models.live_model import DanmakuMessage, LiveSessionResult, RoomInfo, format_time
from src.services.live_parse import (
    WS_OP_AUTH,
    WS_OP_AUTH_REPLY,
    WS_OP_HEARTBEAT,
    WS_OP_HEARTBEAT_REPLY,
    WS_OP_MESSAGE,
    _to_int,
    build_auth_payload,
    build_packet,
    build_record,
    is_danmaku_cmd,
    parse_auth_reply,
    parse_heartbeat_reply,
    parse_history_item,
    parse_room_info,
    parse_ws_payload,
)
from src.services.login import LoginService
from src.urls.live_urls import LiveUrls

logger = logging.getLogger(__name__)

# listen_danmaku 的结束原因（写入 LiveSessionResult.stop_reason 与 meta.json）
STOP_DURATION = "duration"  # 达到 duration 秒
STOP_MAX_COUNT = "max_count"  # 归档条数达到 max_count
STOP_INTERRUPTED = "interrupted"  # Ctrl+C 手动中断
STOP_ROOM_END = "room_end"  # 房间未开播/已下播（stop_on_room_end）
STOP_ERROR = "error"  # 连续重连失败

_LIVE_REFERER = "https://live.bilibili.com/"
_LIVE_HEADERS = {"Referer": _LIVE_REFERER}

# 心跳约 30 秒一次（服务端 60 秒无心跳强制断开），25 秒留出余量
_HEARTBEAT_INTERVAL = 25.0
# 看门狗：心跳回复约 25 秒一次，超过该时长完全无数据视为连接已死
_RX_TIMEOUT = 120.0
_CONNECT_TIMEOUT = 10.0
_AUTH_TIMEOUT = 10.0
_RECONNECT_BASE = 2.0
_RECONNECT_MAX = 30.0
_HOSTS_PER_ATTEMPT = 3  # 每次重连最多尝试的 host 数
_MAX_ERROR_LOGS = 10

# 默认只归档弹幕；message_types="all" 时过滤掉这些高频噪声消息
_DEFAULT_MESSAGE_TYPES = frozenset({"DANMU_MSG"})
_NOISY_CMDS = frozenset({
    "STOP_LIVE_ROOM_LIST",  # 全站停播房间列表（单条几十 KB）
    "ONLINE_RANK_COUNT", "ONLINE_RANK_V2", "ONLINE_RANK_V3", "ONLINE_RANK_TOP3",
    "HOT_RANK_CHANGED", "HOT_RANK_CHANGED_V2", "HOT_RANK_SETTLEMENT", "HOT_RANK_SETTLEMENT_V2",
    "AREA_RANK_CHANGED", "POPULAR_RANK_CHANGED",
    "ROOM_REAL_TIME_MESSAGE_UPDATE",
})

_BEIJING = timezone(timedelta(hours=8))


class _RecvTimeout(TimeoutError):
    """select 等待窗口内没有新数据（正常静默期，不是错误）。"""


def _socket_has_buffered_data(sock) -> bool:
    """SSL 层已解密但未读取的数据：select 对 TLS 内部缓冲不可见，需单独检查。"""
    pending = getattr(sock, "pending", None)
    if not callable(pending):
        return False
    try:
        return pending() > 0
    except Exception:  # noqa: BLE001 SSL 层异常交由上层重连兜底
        return False


def _recv_now(ws) -> bytes:
    raw = ws.recv()
    if raw in ("", b""):  # close/control 帧
        raise ConnectionError("服务端已关闭连接")
    return raw.encode("utf-8") if isinstance(raw, str) else raw


def _normalize_message_types(message_types) -> Optional[frozenset]:
    """归一化 message_types：None=默认只收弹幕；"all"=全部（返回 None 哨兵）；列表=显式集合。"""
    if message_types is None:
        return _DEFAULT_MESSAGE_TYPES
    if isinstance(message_types, str):
        if message_types.strip().lower() == "all":
            return None
        return frozenset({message_types.strip()})
    types = frozenset(str(item).strip() for item in message_types if str(item).strip())
    if not types:
        raise ValueError("message_types 不能为空集合；None=默认只收弹幕，'all'=全部")
    return types


def _accepts(cmd: str, types: Optional[frozenset]) -> bool:
    if types is None:  # "all"：过滤高频噪声
        return cmd not in _NOISY_CMDS
    if "DANMU_MSG" in types and is_danmaku_cmd(cmd):
        return True
    return cmd in types


def _reconnect_delay(failures: int) -> float:
    """指数退避 + 抖动（2s → 30s 封顶）。"""
    base = min(_RECONNECT_BASE * (2 ** (failures - 1)), _RECONNECT_MAX)
    return base + random.uniform(0, 1.0)


def _display_line(record: dict) -> str:
    """非弹幕记录的打印行（TXT 只写弹幕，其他类型仅 JSONL + 控制台）。"""
    parts = [f"[{record.get('time', '')}]", f"<{record.get('type', '?')}>"]
    if record.get("uname"):
        parts.append(str(record["uname"]))
    if record.get("text"):
        parts.append(str(record["text"]))
    elif record.get("gift"):
        parts.append(f"{record['gift']} ×{record.get('num', 1)}")
    return " ".join(parts)


def _alloc_session_dir(base_dir: Path, room_id: int) -> Path:
    """分配场次目录 {base}/{room_id}/{YYYY-MM-DD_HHMMSS}/（同秒冲突时追加 _2、_3…）。"""
    room_dir = base_dir / str(room_id)
    stamp = datetime.fromtimestamp(time.time(), _BEIJING).strftime("%Y-%m-%d_%H%M%S")
    index = 1
    while True:
        candidate = room_dir / (stamp if index == 1 else f"{stamp}_{index}")
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            index += 1


class _SessionWriter:
    """一次监听会话的落盘：danmaku.jsonl + danmaku.txt + meta.json。"""

    def __init__(self, base_dir: Path, room: RoomInfo, account_uid: int, started_at: float):
        self.dir = _alloc_session_dir(base_dir, room.room_id)
        self.jsonl_path = self.dir / "danmaku.jsonl"
        self.txt_path = self.dir / "danmaku.txt"
        self.meta_path = self.dir / "meta.json"
        self._jsonl = self.jsonl_path.open("a", encoding="utf-8")
        self._txt = self.txt_path.open("a", encoding="utf-8")
        self._meta = {
            "version": 1,
            "room": {
                "room_id": room.room_id,
                "uid": room.uid,
                "title": room.title,
                "area_name": room.area_name,
                "live_status": room.live_status,
                "online": room.online,
            },
            "account_uid": account_uid,
            "started_at": format_time(started_at, with_date=True),
            "started_ts": started_at,
            "status": "recording",
        }
        self._write_meta()

    def write_record(self, record: dict) -> None:
        self._jsonl.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._jsonl.flush()

    def write_text(self, line: str) -> None:
        self._txt.write(line + "\n")
        self._txt.flush()

    def finalize(self, result: LiveSessionResult) -> None:
        self._meta.update({
            "ended_at": format_time(result.ended_at, with_date=True),
            "ended_ts": result.ended_at,
            "duration": round(result.duration, 1),
            "status": result.stop_reason or "stopped",
            "counts": result.counts,
            "saved": result.saved,
            "popularity": result.popularity,
            "reconnects": result.reconnects,
            "errors": result.errors,
        })
        self._write_meta()
        self._jsonl.close()
        self._txt.close()

    def _write_meta(self) -> None:
        self.meta_path.write_text(
            json.dumps(self._meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class LiveService:
    """B 站直播服务：房间信息、最近弹幕、实时弹幕监听录制、发送弹幕。

    [登录要求] 实时弹幕必须登录：实测匿名（uid=0）WS 认证会被服务端静默断开，
    认证使用当前 cookie 的登录 mid；发送弹幕还需 cookie 中的 bili_jct。
    """

    def __init__(self, session: Optional[BiliSession] = None, default_dir=None, ws_factory=None):
        """
        :param session: 统一请求会话；None 时使用当前账号 cookie 新建
        :param default_dir: 弹幕落盘根目录；默认 output/live
        :param ws_factory: WebSocket 连接工厂（默认 websocket.create_connection；单测可注入假实现）
        """
        self.session = session if session is not None else BiliSession()
        self.default_dir = Path(default_dir) if default_dir is not None else LIVE_OUTPUT_DIR
        self._ws_factory = ws_factory if ws_factory is not None else websocket.create_connection

    # ---- 房间信息 ----

    def get_room_info(self, room_id: int | str) -> RoomInfo:
        """获取直播间信息（免登录；支持短号，返回真实房间号）。"""
        data = self.session.get(LiveUrls.ROOM_INFO, params={"room_id": room_id}, headers=_LIVE_HEADERS)
        return parse_room_info(data)

    # ---- 最近弹幕快照 ----

    def fetch_recent_danmaku(self, room_id: int | str) -> list[DanmakuMessage]:
        """获取直播间最近的弹幕（实测仅最近约 10 条；房间不在播时通常为空）。

        注意：该接口实测必须带 WBI 签名，否则静默返回空列表。
        """
        params = {"roomid": room_id, "room_type": 0}
        get_wbi(params)
        data = self.session.get(LiveUrls.DANMU_HISTORY, params=params, headers=_LIVE_HEADERS)
        items = data.get("room") if isinstance(data, dict) else None
        messages = [parse_history_item(item) for item in (items or [])]
        return [message for message in messages if message is not None]

    # ---- 实时监听录制 ----

    def listen_danmaku(
        self,
        room_id: int | str,
        *,
        duration: Optional[float] = None,
        max_count: Optional[int] = None,
        message_types=None,
        save: bool = True,
        save_dir=None,
        print_messages: bool = False,
        stop_on_room_end: bool = False,
        room_check_interval: float = 60.0,
        max_reconnects: int = 5,
        on_message: Optional[Callable[[dict], None]] = None,
    ) -> LiveSessionResult:
        """实时监听直播间弹幕（WebSocket 长连接），边收边落盘。

        停止条件（先满足者生效，写入结果的 stop_reason）：
        - duration 秒到期（STOP_DURATION）；
        - 归档条数达到 max_count（STOP_MAX_COUNT）；
        - Ctrl+C 中断：会话正常收尾后返回（STOP_INTERRUPTED）；
        - stop_on_room_end 且房间未开播/已下播（STOP_ROOM_END）；
        - 连续重连失败超过 max_reconnects（STOP_ERROR）。

        :param message_types: 归档范围。None（默认）=只收弹幕（含 DANMU_MSG 变体）；
                              "all"=全部（自动过滤停播列表/榜单等高频噪声）；也可显式传 cmd 列表。
        :param save: 是否落盘到 output/live/{room_id}/{场次时间}/（JSONL + TXT + meta.json）
        :param save_dir: 落盘根目录覆盖（默认 self.default_dir）
        :param on_message: 每条归档记录的回调（dict，与 JSONL 行一致）；回调异常会中断监听
        :param print_messages: 是否在控制台实时打印
        :param stop_on_room_end: 房间未开播/已下播时自动停止（每 room_check_interval 秒检查一次）
        :return: LiveSessionResult（落盘路径、条数统计、停止原因等）
        """
        if duration is not None and duration <= 0:
            raise ValueError("duration 必须为正数")
        if max_count is not None and max_count <= 0:
            raise ValueError("max_count 必须为正数")
        types = _normalize_message_types(message_types)

        room = self.get_room_info(room_id)
        real_id = room.room_id or _to_int(room_id)
        result = LiveSessionResult(room_id=real_id, started_at=time.time())

        if stop_on_room_end and not room.living:
            result.ended_at = result.started_at
            result.stop_reason = STOP_ROOM_END
            return result

        uid = LoginService(session=self.session).get_mid()
        if not uid:
            raise BiliAuthError("实时弹幕需要登录态：服务端会拒绝匿名连接（uid=0），请先扫码登录")

        writer = None
        if save:
            base_dir = Path(save_dir) if save_dir is not None else self.default_dir
            writer = _SessionWriter(base_dir, room, uid, result.started_at)
            result.session_dir = writer.dir
            result.jsonl_path = writer.jsonl_path
            result.txt_path = writer.txt_path
            result.meta_path = writer.meta_path

        stop_reason = ""
        deadline = result.started_at + duration if duration is not None else None
        ws = None
        consecutive_failures = 0
        last_beat = 0.0
        last_rx = time.time()
        last_room_check = time.time()

        try:
            while True:
                now = time.time()
                if deadline is not None and now >= deadline:
                    stop_reason = STOP_DURATION
                    break
                if max_count is not None and result.saved >= max_count:
                    stop_reason = STOP_MAX_COUNT
                    break

                if ws is None:
                    try:
                        ws = self._connect(real_id, uid)
                        consecutive_failures = 0
                        last_beat = last_rx = time.time()
                        logger.info("【直播弹幕】已连接弹幕服务器（房间 %s）", real_id)
                    except Exception as exc:  # noqa: BLE001 连接失败统一走退避重试
                        consecutive_failures += 1
                        result.reconnects += 1
                        self._record_error(result, f"连接失败：{exc}")
                        if consecutive_failures > max_reconnects:
                            stop_reason = STOP_ERROR
                            break
                        self._sleep(_reconnect_delay(consecutive_failures), deadline)
                        continue

                try:
                    payload = self._recv_payload(ws, timeout=1.0)
                except _RecvTimeout:
                    payload = None
                except Exception as exc:  # noqa: BLE001 websocket 异常 / OSError / 帧错位
                    self._record_error(result, f"连接中断：{exc}")
                    self._close(ws)
                    ws = None
                    self._sleep(1.0, deadline)
                    continue

                now = time.time()
                if payload is not None:
                    last_rx = now
                    self._handle_payload(payload, result, types, writer, on_message, print_messages)
                    if max_count is not None and result.saved >= max_count:
                        stop_reason = STOP_MAX_COUNT
                        break

                if ws is not None and now - last_beat >= _HEARTBEAT_INTERVAL:
                    try:
                        ws.send(build_packet(WS_OP_HEARTBEAT))
                        last_beat = now
                    except Exception as exc:  # noqa: BLE001 发送失败按断线处理
                        self._record_error(result, f"心跳发送失败：{exc}")
                        self._close(ws)
                        ws = None

                if ws is not None and now - last_rx > _RX_TIMEOUT:
                    logger.warning("【直播弹幕】%.0f 秒无任何数据，重建连接", _RX_TIMEOUT)
                    self._close(ws)
                    ws = None

                if stop_on_room_end and now - last_room_check >= room_check_interval:
                    last_room_check = now
                    try:
                        if not self.get_room_info(real_id).living:
                            logger.info("【直播弹幕】房间已下播，停止监听")
                            stop_reason = STOP_ROOM_END
                            break
                    except Exception as exc:  # noqa: BLE001 状态检查失败不中断录制
                        logger.warning("【直播弹幕】房间状态检查失败：%s", exc)
        except KeyboardInterrupt:
            stop_reason = STOP_INTERRUPTED
            logger.info("【直播弹幕】收到中断信号，停止监听并收尾")
        finally:
            self._close(ws)

        result.ended_at = time.time()
        result.stop_reason = stop_reason
        if writer is not None:
            writer.finalize(result)
        return result

    # ---- 发送弹幕 ----

    def send_danmaku(
        self,
        room_id: int | str,
        text: str,
        *,
        color: int = 16777215,
        fontsize: int = 25,
        mode: int = 1,
    ) -> dict:
        """发送直播间弹幕（写操作，需要登录态；默认白色 25 号滚动弹幕）。

        :param color: 颜色（十进制 RGB，默认 16777215 = 白色）
        :param fontsize: 字号（默认 25）
        :param mode: 弹幕模式（1 滚动）
        :return: 接口返回的 data 字段
        """
        content = (text or "").strip()
        if not content:
            raise ValueError("弹幕内容不能为空")
        csrf = self.session.cookie.bili_jct
        if not csrf:
            raise BiliAuthError("发送弹幕需要登录（cookie 缺少 bili_jct）")
        data = {
            "msg": content,
            "color": int(color),
            "fontsize": int(fontsize),
            "mode": int(mode),
            "rnd": int(time.time()),
            "roomid": room_id,
            "csrf": csrf,
            "csrf_token": csrf,
        }
        return self.session.post(LiveUrls.SEND_DANMU, data=data, headers=_LIVE_HEADERS)

    # ---- 内部：连接与消息处理 ----

    def _connect(self, room_id: int, uid: int):
        """获取弹幕服务器信息并建立一条已认证的连接（按 host 列表依次尝试）。"""
        params = {"id": room_id, "type": 0}
        get_wbi(params)  # 实测必须签名，否则 -352 风控
        info = self.session.get(LiveUrls.DANMU_INFO, params=params, headers=_LIVE_HEADERS)
        token = str(info.get("token") or "")
        hosts = info.get("host_list") or []
        if not token or not hosts:
            raise BiliError(f"getDanmuInfo 返回异常：token={'有' if token else '无'}，host 数={len(hosts)}")

        buvid = self._buvid()
        last_error: Optional[Exception] = None
        for host_info in hosts[:_HOSTS_PER_ATTEMPT]:
            if not isinstance(host_info, dict):
                continue
            host = str(host_info.get("host") or "")
            if not host:
                continue
            port = _to_int(host_info.get("wss_port")) or 443
            ws = None
            try:
                ws = self._ws_factory(
                    f"wss://{host}:{port}/sub",
                    timeout=_CONNECT_TIMEOUT,
                    header={"User-Agent": UserAgent().pcChrome, "Referer": _LIVE_REFERER},
                    origin=_LIVE_REFERER,
                    cookie=self.session.cookie.cookie or None,
                )
                self._authenticate(ws, room_id, uid, token, buvid)
                return ws
            except Exception as exc:  # noqa: BLE001 换下一个 host 继续尝试
                last_error = exc
                self._close(ws)
                logger.warning("【直播弹幕】连接 %s 失败：%s", host, exc)
        raise last_error or BiliError("弹幕服务器连接失败：host 列表为空")

    def _authenticate(self, ws, room_id: int, uid: int, token: str, buvid: str) -> None:
        """发送认证包并等待 op=8 回复（code != 0 视为失败）。"""
        ws.send(build_packet(WS_OP_AUTH, build_auth_payload(room_id, uid, token, buvid=buvid)))
        deadline = time.time() + _AUTH_TIMEOUT
        while time.time() < deadline:
            try:
                payload = self._recv_payload(ws, timeout=min(1.0, max(0.1, deadline - time.time())))
            except _RecvTimeout:
                continue
            for packet in parse_ws_payload(payload):
                if packet.op != WS_OP_AUTH_REPLY:
                    continue
                reply = parse_auth_reply(packet.body)
                if _to_int(reply.get("code")) != 0:
                    raise BiliError(f"弹幕认证失败：{reply}")
                return
        raise TimeoutError("弹幕认证超时（未收到认证回复 op=8）")

    @staticmethod
    def _recv_payload(ws, timeout: float) -> bytes:
        """在 timeout 秒内读取一帧 WS 载荷。

        select 先确认可读再 recv，避免套接字超时落在帧中间导致流错位；
        超时抛 _RecvTimeout（静默期正常），连接断开抛 ConnectionError。
        """
        sock = getattr(ws, "sock", None)
        if sock is None:
            raise ConnectionError("连接已关闭")
        deadline = time.time() + timeout
        while True:
            if _socket_has_buffered_data(sock):
                return _recv_now(ws)
            remaining = deadline - time.time()
            if remaining <= 0:
                raise _RecvTimeout()
            ready, _, _ = select.select([sock], [], [], min(0.5, remaining))
            if ready:
                return _recv_now(ws)

    def _handle_payload(self, payload: bytes, result: LiveSessionResult, types, writer,
                        on_message, print_messages: bool) -> None:
        """解析一帧载荷：心跳回复更新人气；业务消息过滤后回调与落盘。"""
        for packet in parse_ws_payload(payload):
            if packet.op == WS_OP_HEARTBEAT_REPLY:
                result.popularity = parse_heartbeat_reply(packet.body)
                continue
            if packet.op != WS_OP_MESSAGE:
                continue
            try:
                msg = json.loads(packet.body)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            cmd = str(msg.get("cmd") or "")
            if not cmd or not _accepts(cmd, types):
                continue
            record, text_line = build_record(cmd, msg, time.time())
            if record is None:
                continue
            result.counts[cmd] = result.counts.get(cmd, 0) + 1
            result.saved += 1
            if on_message is not None:
                on_message(record)
            if writer is not None:
                writer.write_record(record)
                if text_line:
                    writer.write_text(text_line)
            if print_messages:
                print(text_line or _display_line(record), flush=True)

    def _buvid(self) -> str:
        """会话 cookie 中的 buvid3（getDanmuInfo 之后通常已由服务端种上；可为空）。"""
        try:
            return self.session.session.cookies.get("buvid3", "") or ""
        except Exception:  # noqa: BLE001 cookie jar 结构异常时按无 buvid 处理
            return ""

    @staticmethod
    def _close(ws) -> None:
        if ws is None:
            return
        try:
            ws.close()
        except Exception:  # noqa: BLE001 关闭失败不影响后续重连
            pass

    @staticmethod
    def _record_error(result: LiveSessionResult, message: str) -> None:
        logger.warning("【直播弹幕】%s", message)
        result.errors.append(f"{format_time(time.time(), with_date=True)} {message}")
        del result.errors[:-_MAX_ERROR_LOGS]  # 只保留最近 10 条

    @staticmethod
    def _sleep(seconds: float, deadline: Optional[float]) -> None:
        """切片睡眠：及时响应 duration 到期（Ctrl+C 由 KeyboardInterrupt 直接打断）。"""
        end = time.time() + seconds
        if deadline is not None:
            end = min(end, deadline)
        while True:
            remaining = end - time.time()
            if remaining <= 0:
                return
            time.sleep(min(0.5, remaining))
