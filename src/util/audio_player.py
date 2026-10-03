"""音频播放：把本地 WAV 播到系统默认音频设备。

[实现] Windows 标准库 winsound（零依赖）；播放采用异步启动 + 按 wav 时长等待，
等待期间可被 stop() 打断（SND_PURGE 尝试立即停声，失败也最多播完当前一条）。

[接口] AudioPlayer 协议仅 play(path)/stop()；单测可注入假实现。

[限制] winsound 无法控制音量、不支持指定输出设备（走系统默认设备，即推流软件采到的
       那路声音）；仅支持 WAV（TTS 服务输出即 32kHz 单声道 WAV）。
"""

import threading
import time
import wave
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class AudioPlayer(Protocol):
    """播放器接口：play 阻塞到播完（或被打断），stop 立即打断当前播放。"""

    def play(self, path) -> None:  # pragma: no cover - 协议定义
        ...

    def stop(self) -> None:  # pragma: no cover - 协议定义
        ...


def wav_duration(path) -> Optional[float]:
    """读取 WAV 时长（秒）；非 WAV/损坏文件返回 None。"""
    try:
        with wave.open(str(path), "rb") as reader:
            rate = reader.getframerate()
            if rate <= 0:
                return None
            return reader.getnframes() / float(rate)
    except (wave.Error, OSError, EOFError):
        return None


class WinsoundPlayer:
    """Windows 播放器：异步启动 + 时长等待（可打断）。"""

    def __init__(self):
        try:
            import winsound
        except ImportError as exc:  # 非 Windows 平台
            raise RuntimeError("WinsoundPlayer 仅支持 Windows（winsound 不可用）") from exc
        self._winsound = winsound
        self._stop_event = threading.Event()

    def play(self, path) -> None:
        """播放 wav，阻塞到播完或被 stop() 打断；文件缺失/损坏抛异常。"""
        target = Path(path)
        if not target.exists():
            raise FileNotFoundError(f"音频文件不存在：{target}")
        duration = wav_duration(target)
        self._stop_event.clear()
        self._winsound.PlaySound(str(target),
                                 self._winsound.SND_FILENAME | self._winsound.SND_ASYNC)
        deadline = time.monotonic() + (duration + 0.1 if duration is not None else 5.0)
        while time.monotonic() < deadline:
            if self._stop_event.wait(0.05):
                break
        if self._stop_event.is_set():
            self._purge()

    def stop(self) -> None:
        """打断当前播放（并阻止后续等待）。"""
        self._stop_event.set()
        self._purge()

    def _purge(self) -> None:
        try:
            self._winsound.PlaySound(None, self._winsound.SND_PURGE)
        except RuntimeError:  # 无正在播放的声音时个别系统会报错，忽略
            pass
