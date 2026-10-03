"""直播弹幕语音播报示例：弹幕 → GPT-SoVITS 合成 → 本机播放。

前置：
- GPT-SoVITS 的 tts_server.py 已在运行，**未运行则 speak() 会自动拉起**（默认开启）：
  脚本位置自动探测（项目上级目录 / 用户目录下的 GPT-SoVITS 仓库），也可用环境变量
  TTS_SERVER_SCRIPT（脚本）与 TTS_PYTHON（conda 解释器）显式指定；
  服务地址默认 127.0.0.1:9881，可用 TTS_SERVER_URL 改。
- 实时弹幕需要登录态（与 examples/live.py 相同）。
注意：调用 speak() 会真实合成并播放声音（走系统默认音频设备）。

[运行]
    python -m examples.live_speech
"""

from src.services import LiveSpeechService
from src.services.live_speech import SpeechFilter
from src.services.tts import TtsService

ROOM = 25774901  # 你的直播间（开播后开这个脚本才有弹幕）
ROLE = "阿罗娜（中配）"  # GPT-SoVITS 角色名（一场直播固定一个，换角色会重载权重数秒）


def show_tts() -> None:
    """查看 TTS 服务状态与可用角色。"""
    tts = TtsService()
    health = tts.health()
    print("TTS 服务：", health if health else "未启动（调用 speak() 时会自动拉起，也可手动运行 tts_server.py）")
    if health:
        for role in tts.list_roles():
            note = f"（{role['note']}）" if role.get("note") else ""
            print(f"  - {role['name']}{note}")


def speak(duration: float = 300) -> None:
    """监听直播弹幕并逐条播报（Ctrl+C 停止；duration 秒到点自动停）。

    常用参数（详见 LiveSpeechService.run 的 docstring）：
    - template: 播报模板，默认 "{uname}说：{text}"（带昵称）；只念内容可传 "{text}"
    - speech_filter: 过滤规则；默认不过滤。SpeechFilter.preset_standard(anchor_uid) 为推荐套件
      （长度 2~40、跳过指令前缀、同人 1 分钟 3 条、去重、忽略主播自己）
    - queue_size: 积压上限（默认 3，满则丢最旧保最新）
    - stop_on_room_end=True 下播自动停；save=False 不落盘弹幕存档
    """
    service = LiveSpeechService()
    result = service.run(ROOM, ROLE, duration=duration)
    print(f"\n结束（{result.stop_reason}）：播报 {result.spoken} 条 / 跳过 {result.skipped} / "
          f"丢弃 {result.dropped} / 失败 {result.failures}")
    if result.listen.session_dir is not None:
        print(f"弹幕存档：{result.listen.session_dir}")


if __name__ == "__main__":
    # 默认只查看 TTS 状态与角色，避免直接开声。
    # show_tts()
    # print("\n如需播报，调用 speak(duration=300)（会真实播放声音）。")
    speak(duration=36000)
