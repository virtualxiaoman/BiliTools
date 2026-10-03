"""LiveSpeechService / SpeechFilter 单元测试（不联网、不出声）。

假弹幕服务喂完弹幕后会等待 worker 排空队列（done 条件），避免"停止时机"造成的时序抖动。
"""

import threading
import time
from pathlib import Path

import pytest

from src.models.live_model import LiveSessionResult
from src.services.live_speech import LiveSpeechService, SpeechFilter


def _danmaku(text, uid=1, uname="丰辰", guard_level=0, is_admin=0):
    return {"type": "DANMU_MSG", "text": text, "uid": uid, "uname": uname,
            "guard_level": guard_level, "is_admin": is_admin}


class FakeTts:
    def __init__(self, on_first=None):
        self.base_url = "http://fake"
        self.autostart = False
        self.calls = []
        self._on_first = on_first  # 第一条合成时的钩子（用于制造"worker 正忙"场景）

    def health(self):
        return {"status": "ok"}

    def synthesize(self, role, text, *, lang="zh", speed=1.0, seed=-1, save_to=None):
        self.calls.append(text)
        if len(self.calls) == 1 and self._on_first is not None:
            self._on_first()
        return Path(f"C:/fake/{len(self.calls)}.wav")


class DownTts(FakeTts):
    def health(self):
        return None


class FailTts(FakeTts):
    def synthesize(self, role, text, **kwargs):
        self.calls.append(text)
        raise RuntimeError("合成失败（模拟）")


class FakePlayer:
    def __init__(self):
        self.played = []
        self.stops = 0

    def play(self, path):
        self.played.append(str(path))

    def stop(self):
        self.stops += 1


class FakeLive:
    """假弹幕服务：喂完预置弹幕后等待 done 条件（保证 worker 已处理），再返回监听结果。"""

    def __init__(self, records, done=None):
        self.records = records
        self.done = done
        self.kwargs = None
        self.called = False

    def _wait_done(self):
        if self.done is None:
            return
        deadline = time.time() + 5
        while time.time() < deadline and not self.done():
            time.sleep(0.01)
        assert self.done(), "等待 worker 处理超时"

    def listen_danmaku(self, room_id, **kwargs):
        self.called = True
        self.kwargs = kwargs
        for record in self.records:
            kwargs["on_message"](record)
        self._wait_done()
        return LiveSessionResult(room_id=350353, stop_reason="duration")


class GatedLive(FakeLive):
    """先喂第一条，等 worker 取走并开始合成后，再喂剩余弹幕（验证积压丢弃）。"""

    def __init__(self, records, worker_took_first: threading.Event, done=None):
        super().__init__(records, done=done)
        self._worker_took_first = worker_took_first

    def listen_danmaku(self, room_id, **kwargs):
        self.called = True
        self.kwargs = kwargs
        handle = kwargs["on_message"]
        handle(self.records[0])
        assert self._worker_took_first.wait(timeout=5), "worker 未取走第一条"
        for record in self.records[1:]:
            handle(record)
        self._wait_done()
        return LiveSessionResult(room_id=350353, stop_reason="duration")


def _service(records, tts=None, player=None, live_cls=FakeLive, done=None, **live_kwargs):
    fake_live = live_cls(records, done=done, **live_kwargs)
    service = LiveSpeechService(tts=tts or FakeTts(), player=player or FakePlayer(), live=fake_live)
    return service, fake_live


# ---- 主流程 ----

def test_run_speaks_with_nickname_template():
    player, tts = FakePlayer(), FakeTts()
    records = [_danmaku("没胃口"), _danmaku("喝点什么", uid=2, uname="彼方")]
    service, fake_live = _service(records, tts=tts, player=player,
                                  done=lambda: len(player.played) == 2)
    result = service.run(350353, "阿罗娜（中配）", duration=1)

    assert result.spoken == 2 and result.failures == 0 and result.skipped == 0
    assert tts.calls == ["丰辰说：没胃口", "彼方说：喝点什么"]
    assert player.played == [str(Path("C:/fake/1.wav")), str(Path("C:/fake/2.wav"))]
    assert result.stop_reason == "duration"
    assert player.stops >= 1  # 收尾打断播放
    # 参数透传给监听层（默认落盘开启）
    assert fake_live.kwargs["save"] is True and fake_live.kwargs["duration"] == 1


def test_run_plain_template_and_save_off():
    tts = FakeTts()
    service, fake_live = _service([_danmaku("你好")], tts=tts, done=lambda: len(tts.calls) == 1)
    result = service.run(350353, "r", template="{text}", save=False)
    assert tts.calls == ["你好"]
    assert fake_live.kwargs["save"] is False
    assert result.spoken == 1


def test_run_applies_filter():
    tts = FakeTts()
    records = [_danmaku("这是一条很长的弹幕内容超过限制"), _danmaku("短弹幕")]
    service, _ = _service(records, tts=tts, done=lambda: len(tts.calls) == 1)
    result = service.run(350353, "r", speech_filter=SpeechFilter(max_chars=5))
    assert result.skipped == 1 and result.spoken == 1
    assert tts.calls == ["丰辰说：短弹幕"]  # 超长那条被过滤，未合成


def test_run_requires_tts_service():
    player = FakePlayer()
    service, fake_live = _service([], tts=DownTts(), player=player)
    with pytest.raises(RuntimeError, match="TTS 服务未启动"):
        service.run(350353, "r")
    assert fake_live.called is False  # 未开始监听


def test_synthesis_failure_counted_and_continues():
    tts = FailTts()
    records = [_danmaku("a"), _danmaku("b")]
    service, _ = _service(records, tts=tts, done=lambda: len(tts.calls) == 2)
    result = service.run(350353, "r")
    assert result.failures == 2 and result.spoken == 0
    assert result.listen.stop_reason == "duration"


def test_queue_overflow_drops_oldest():
    took_first = threading.Event()
    tts = FakeTts(on_first=lambda: took_first.set())
    records = [_danmaku(f"记录{i}") for i in range(1, 8)]
    service, _ = _service(records, tts=tts,
                          live_cls=GatedLive, worker_took_first=took_first,
                          done=lambda: len(tts.calls) == 4)

    result = service.run(350353, "r", queue_size=3)

    assert result.dropped == 3  # 后到 6 条挤进容量 3 的队列 → 丢 3 条最旧
    assert result.spoken == 4  # 正在合成的 1 条 + 队列保留的最新 3 条
    assert tts.calls == ["丰辰说：记录1", "丰辰说：记录5", "丰辰说：记录6", "丰辰说：记录7"]


# ---- 过滤规则 ----

def test_filter_empty_text_and_defaults_pass_everything():
    rules = SpeechFilter()
    assert rules.should_speak(_danmaku("")) is False  # 空文本始终跳过
    assert rules.should_speak(_danmaku("点歌xxx")) is True  # 默认不过滤
    assert rules.should_speak(_danmaku("a" * 200)) is True


def test_filter_length_prefix_blocklist():
    rules = SpeechFilter(min_chars=2, max_chars=10, skip_prefixes=("点歌", "!"),
                         blocklist=("广告",))
    assert rules.should_speak(_danmaku("短")) is False
    assert rules.should_speak(_danmaku("a" * 11)) is False
    assert rules.should_speak(_danmaku("点歌 起风了")) is False
    assert rules.should_speak(_danmaku("!帮我查天气")) is False
    assert rules.should_speak(_danmaku("这是广告内容")) is False
    assert rules.should_speak(_danmaku("正常弹幕")) is True


def test_filter_guard_only_and_ignore_self():
    rules = SpeechFilter(guard_only=True, ignore_self=True, anchor_uid=506925078)
    assert rules.should_speak(_danmaku("舰长的话", guard_level=3)) is True
    assert rules.should_speak(_danmaku("房管的话", is_admin=1)) is True
    assert rules.should_speak(_danmaku("普通观众")) is False
    assert rules.should_speak(_danmaku("主播自己", uid=506925078, guard_level=3)) is False


def test_filter_dedupe_window():
    rules = SpeechFilter(dedupe_window=30.0)
    assert rules.should_speak(_danmaku("复读机", uid=7), now=1000.0) is True
    assert rules.should_speak(_danmaku("复读机", uid=7), now=1010.0) is False
    assert rules.should_speak(_danmaku("复读机", uid=7), now=1031.0) is True  # 窗口过期
    assert rules.should_speak(_danmaku("别的内容", uid=7), now=1031.5) is True
    assert rules.should_speak(_danmaku("复读机", uid=8), now=1031.6) is True  # 不同用户互不影响


def test_filter_per_user_limit():
    rules = SpeechFilter(per_user_limit=2, per_user_window=60.0)
    assert rules.should_speak(_danmaku("第一条", uid=7), now=100.0) is True
    assert rules.should_speak(_danmaku("第二条", uid=7), now=110.0) is True
    assert rules.should_speak(_danmaku("第三条", uid=7), now=120.0) is False
    assert rules.should_speak(_danmaku("第四条", uid=8), now=121.0) is True  # 其他用户不受限
    assert rules.should_speak(_danmaku("第五条", uid=7), now=165.0) is True  # 窗口滚出后可再念


def test_filter_preset_standard():
    rules = SpeechFilter.preset_standard(anchor_uid=506925078)
    assert (rules.min_chars, rules.max_chars) == (2, 40)
    assert rules.per_user_limit == 3 and rules.dedupe_window == 30.0
    assert rules.should_speak(_danmaku("主播", uid=506925078)) is False
    assert rules.should_speak(_danmaku("点歌 起风了")) is False
    assert rules.should_speak(_danmaku("正常弹幕")) is True
