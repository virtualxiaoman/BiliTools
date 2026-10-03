"""直播弹幕示例：房间信息 / 最近弹幕 / 实时监听录制 / 发送弹幕。

查询与监听均为只读操作；发送弹幕是写操作，默认只保留注释示例、不执行。
实时弹幕需要登录态（服务端拒绝匿名连接），监听录制会写入
output/live/{room_id}/{场次时间}/（danmaku.jsonl + danmaku.txt + meta.json）。

[运行]
    python -m examples.live
"""

from src.services import LiveService

# 示例房间号（可换成任意直播间；短号会自动解析为真实房间号）
ROOM = 25774901


def show_room_info() -> None:
    """房间信息：主播、标题、开播状态、在线人数。"""
    info = LiveService().get_room_info(ROOM)
    state = {0: "未开播", 1: "直播中", 2: "轮播"}.get(info.live_status, str(info.live_status))
    print(f"房间 {info.room_id}（短号 {info.short_id or '-'}）｜{state}")
    print(f"标题：{info.title}｜分区：{info.area_name}｜在线：{info.online}｜关注：{info.attention}")
    live_time = info.live_time if not info.live_time.startswith("0000") else "-"
    print(f"开播时间：{live_time}")


def fetch_recent() -> None:
    """最近弹幕快照（实测仅最近约 10 条；房间不在播时通常为空）。"""
    messages = LiveService().fetch_recent_danmaku(ROOM)
    print(f"最近弹幕 {len(messages)} 条：")
    for message in messages:
        print("  ", message.to_text_line())


def record(duration: float = 60) -> None:
    """实时监听并落盘（Ctrl+C 可随时停止，到 duration 秒自动停止）。

    常用参数（详见 LiveService.listen_danmaku 的 docstring）：
    - message_types: None（默认）只收弹幕；"all" 收礼物/SC/上舰等全部（自动过滤榜单噪声）；
      也可显式传 ["DANMU_MSG", "SUPER_CHAT_MESSAGE", "SEND_GIFT", "GUARD_BUY"]
    - save=False 时只回调/打印，不落盘；stop_on_room_end=True 时下播自动停止；
    - max_count=200 限制归档条数；on_message=回调 可接入自定义处理（如实时分析）。
    """
    result = LiveService().listen_danmaku(
        ROOM,
        duration=duration,
        print_messages=True,
    )
    print(f"监听结束（{result.stop_reason}）：{result.duration:.0f} 秒，"
          f"收到 {result.total} 条，归档 {result.saved} 条，重连 {result.reconnects} 次")
    if result.session_dir is not None:
        print(f"落盘目录：{result.session_dir}")


def send_once() -> None:
    """发送一条弹幕（写操作，谨慎调用；先核对房间号再取消注释）。"""
    result = LiveService().send_danmaku(ROOM, "我喜欢你")
    print(result)
    print("send_once 已注释：确认房间号无误后，取消函数内注释即可发送。")


if __name__ == "__main__":
    # 默认只查房间信息，避免误触发长时间监听或写操作。
    show_room_info()
    print("\n如需其他功能，调用 fetch_recent() / record(duration=60) / send_once()。")
    fetch_recent()
    # record(duration=60)
    send_once()
