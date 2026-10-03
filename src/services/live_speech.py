"""直播弹幕语音播报：弹幕 → 过滤 → 有界队列 → TTS 合成 → 本地播放。

[工作流]
    LiveService.listen_danmaku(room, on_message=handle)   ← 同一条 WS 连接同时录制落盘
        └ handle（WS 接收线程内，只做过滤+入队，非阻塞）
    Speech worker（独立线程）：出队 → TtsService.synthesize → AudioPlayer.play（阻塞播放）
    监听结束（时长/中断/下播）→ 停止 worker、打断播放、汇总统计

[设计约束（实测 2026-10-03）]
- 播放时长 ≈ 合成耗时的 3 倍 → 队列必须有界（默认 3），满时丢弃最旧、保最新；
- GPT-SoVITS 换角色会重载权重（数秒）→ 一场直播固定一个角色；
- 播放走系统默认音频设备（推流软件捕获的就是这一路）；winsound 无音量控制。
"""

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional

from src.models.live_model import LiveSessionResult
from src.services.live import LiveService
from src.services.tts import TtsService
from src.util.audio_player import AudioPlayer, WinsoundPlayer

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = "{uname}说：{text}"


@dataclass
class SpeechFilter:
    """播报过滤规则（默认全部关闭 = 不过滤；空文本/纯表情弹幕始终跳过）。

    判断顺序：忽略主播 → 仅舰长/房管 → 长度 → 指令前缀 → 关键词黑名单 → 重复去重 → 同人限频。
    实例带状态（去重/限频计数），一场直播复用一个实例。
    """

    min_chars: int = 0  # 少于该字数跳过（0=不限）
    max_chars: int = 0  # 超过该字数跳过（0=不限）
    skip_prefixes: tuple = ()  # 命中所列前缀则跳过（如 ("点歌", "!", "！")）
    blocklist: tuple = ()  # 包含所列关键词则跳过
    dedupe_window: float = 0.0  # 秒；同一用户同一内容在该窗口内只念一次（0=关）
    per_user_limit: int = 0  # 每 per_user_window 秒内最多念几条（0=关）
    per_user_window: float = 60.0
    guard_only: bool = False  # 仅念 舰长/提督/总督 或 房管
    ignore_self: bool = False  # 忽略主播自己发的弹幕
    anchor_uid: int = 0  # 主播 mid（ignore_self 判断依据）

    def __post_init__(self):
        self._recent_text = {}  # uid -> (text, ts)
        self._user_times = {}  # uid -> [ts, ...]
        self._lock = threading.Lock()

    @classmethod
    def preset_standard(cls, anchor_uid: int = 0) -> "SpeechFilter":
        """推荐套件（热闹房间用）：2~40 字、跳过指令前缀、同人 1 分钟 3 条、去重、忽略主播自己。"""
        return cls(
            min_chars=2, max_chars=40, skip_prefixes=("点歌", "!", "！", "#", "。"),
            dedupe_window=30.0, per_user_limit=3, per_user_window=60.0,
            ignore_self=True, anchor_uid=anchor_uid,
        )

    def should_speak(self, record: dict, now: Optional[float] = None) -> bool:
        """该弹幕是否应播报（record 为 JSONL 记录 dict：text/uid/guard_level/is_admin）。"""
        now = time.time() if now is None else now
        text = str(record.get("text") or "").strip()
        if not text:
            return False
        uid = int(record.get("uid") or 0)

        with self._lock:
            if self.ignore_self and self.anchor_uid and uid == self.anchor_uid:
                return False
            if self.guard_only and not (int(record.get("guard_level") or 0) > 0
                                        or bool(record.get("is_admin"))):
                return False
            if self.min_chars and len(text) < self.min_chars:
                return False
            if self.max_chars and len(text) > self.max_chars:
                return False
            if self.skip_prefixes and text.startswith(tuple(self.skip_prefixes)):
                return False
            if self.blocklist and any(word in text for word in self.blocklist):
                return False
            if self.dedupe_window > 0:
                last = self._recent_text.get(uid)
                if last is not None and last[0] == text and now - last[1] < self.dedupe_window:
                    return False
            if self.per_user_limit > 0:
                times = [t for t in self._user_times.get(uid, ())
                         if now - t < self.per_user_window]
                self._user_times[uid] = times
                if len(times) >= self.per_user_limit:
                    return False
            # 接受：更新去重/限频状态
            if self.dedupe_window > 0:
                self._recent_text[uid] = (text, now)
            if self.per_user_limit > 0:
                self._user_times[uid].append(now)
        return True


@dataclass
class SpeechSessionResult:
    """一次语音播报会话结果：弹幕监听结果 + 语音统计。"""

    listen: LiveSessionResult
    spoken: int = 0  # 成功播报条数
    skipped: int = 0  # 被过滤条数
    dropped: int = 0  # 积压丢弃条数（保最新策略）
    failures: int = 0  # 合成/播放失败条数
    played_seconds: float = 0.0  # 合成 + 播放耗时累计

    @property
    def stop_reason(self) -> str:
        return self.listen.stop_reason


class LiveSpeechService:
    """弹幕语音播报编排：LiveService（弹幕流）+ TtsService（合成）+ AudioPlayer（播放）。"""

    def __init__(self, tts: Optional[TtsService] = None, player: Optional[AudioPlayer] = None,
                 live: Optional[LiveService] = None, *, default_dir=None):
        """
        :param tts: TTS 客户端；None 时用默认地址（环境变量 TTS_SERVER_URL / 127.0.0.1:9881）
        :param player: 播放器；None 时使用 WinsoundPlayer（单测可注入假实现）
        :param live: 弹幕服务；None 时新建（落盘目录默认 output/live）
        """
        self.tts = tts if tts is not None else TtsService()
        self._player = player
        self.live = live if live is not None else LiveService(default_dir=default_dir)

    def run(
        self,
        room_id,
        role: str,
        *,
        lang: str = "zh",
        speed: float = 1.0,
        template: str = DEFAULT_TEMPLATE,
        speech_filter: Optional[SpeechFilter] = None,
        queue_size: int = 3,
        duration: Optional[float] = None,
        stop_on_room_end: bool = False,
        save: bool = True,
        save_dir=None,
        print_speech: bool = True,
    ) -> SpeechSessionResult:
        """监听直播弹幕并逐条语音播报，直到停止条件满足。

        停止条件与 LiveService.listen_danmaku 一致（时长到期 / Ctrl+C / 下播）；
        队列满时丢弃最旧的一条（保最新，实时感优先）。

        :param role: GPT-SoVITS 角色名（一场直播请固定一个角色，换角色会重载权重）
        :param template: 播报文本模板，可用 {uname} 与 {text}（默认「昵称说：内容」）
        :param speech_filter: 过滤规则；None=不过滤（空文本/纯表情仍跳过）
        :param queue_size: 播报队列上限（默认 3）
        :param save: 是否同时把弹幕落盘（复用 LiveService 的场次目录）
        """
        if self.tts.health() is None:
            if getattr(self.tts, "autostart", False):
                self.tts.ensure_server()
            else:
                raise RuntimeError(
                    f"TTS 服务未启动（{self.tts.base_url}），无法开始语音播报。"
                    "请先运行 GPT-SoVITS 的 tts_server.py。"
                )

        player = self._player if self._player is not None else WinsoundPlayer()
        rules = speech_filter if speech_filter is not None else SpeechFilter()
        pending: "queue.Queue" = queue.Queue(maxsize=max(1, int(queue_size)))
        stop_event = threading.Event()
        lock = threading.Lock()
        counters = {"spoken": 0, "skipped": 0, "dropped": 0, "failures": 0, "seconds": 0.0}
        logger.info("【语音播报】开始：房间=%s 角色=%s 队列上限=%d", room_id, role, pending.maxsize)

        def handle(record: dict) -> None:
            """WS 接收线程内执行：必须快 —— 只做过滤与入队（不做任何网络/磁盘操作）。"""
            if stop_event.is_set():
                return
            if not rules.should_speak(record, time.time()):
                with lock:
                    counters["skipped"] += 1
                return
            try:
                text = str(template).format(uname=record.get("uname") or "某人",
                                            text=record.get("text") or "")
            except (KeyError, IndexError, ValueError):
                text = str(record.get("text") or "")
            item = {"text": text}
            try:
                pending.put_nowait(item)
            except queue.Full:
                try:
                    pending.get_nowait()  # 丢最旧，保最新
                    with lock:
                        counters["dropped"] += 1
                except queue.Empty:
                    pass
                try:
                    pending.put_nowait(item)
                except queue.Full:
                    with lock:
                        counters["dropped"] += 1

        worker = threading.Thread(
            target=self._speak_loop, name="live-speech", daemon=True,
            args=(pending, stop_event, role, lang, speed, player, counters, lock, bool(print_speech)),
        )
        worker.start()
        try:
            listen_result = self.live.listen_danmaku(
                room_id, duration=duration, stop_on_room_end=stop_on_room_end,
                save=save, save_dir=save_dir, on_message=handle,
            )
        finally:
            stop_event.set()
            player.stop()
            try:
                pending.put_nowait(None)  # 唤醒 worker 立即退出
            except queue.Full:
                try:
                    pending.get_nowait()
                except queue.Empty:
                    pass
                try:
                    pending.put_nowait(None)
                except queue.Full:
                    pass
            worker.join(timeout=10.0)

        with lock:
            result = SpeechSessionResult(
                listen=listen_result,
                spoken=counters["spoken"], skipped=counters["skipped"],
                dropped=counters["dropped"], failures=counters["failures"],
                played_seconds=round(counters["seconds"], 2),
            )
        logger.info("【语音播报】结束：播报 %d 条，跳过 %d，丢弃 %d，失败 %d",
                    result.spoken, result.skipped, result.dropped, result.failures)
        return result

    # ---- 内部：播报线程 ----

    def _speak_loop(self, pending: "queue.Queue", stop_event: threading.Event, role: str,
                    lang: str, speed: float, player: AudioPlayer, counters: dict,
                    lock: threading.Lock, print_speech: bool) -> None:
        consecutive_failures = 0
        while not stop_event.is_set():
            try:
                item = pending.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                return
            text = item["text"]
            try:
                started = time.time()
                wav_path = self.tts.synthesize(role, text, lang=lang, speed=speed)
                if stop_event.is_set():  # 合成期间被停止 → 不再播放
                    return
                if print_speech:
                    print(f"[语音] {text}", flush=True)
                player.play(wav_path)
                with lock:
                    counters["spoken"] += 1
                    counters["seconds"] += time.time() - started
                consecutive_failures = 0
            except Exception as exc:  # noqa: BLE001 单条失败不影响后续播报
                with lock:
                    counters["failures"] += 1
                logger.warning("【语音播报】失败：%s", exc)
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    time.sleep(3.0)  # 服务异常（如被关闭）时节流，避免请求风暴
