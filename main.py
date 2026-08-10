"""BiliTools 命令行入口（简洁版）。

用法：
    python main.py <command> [args]

可用命令（示例）：
    info   BV号       获取视频信息
    video  BV号       下载视频（含音频）
    cover  BV号       下载封面
    rank              获取热门视频

完整示例见 examples/quick_start.py
"""

import sys

from src.services import RankService, VideoService


def cmd_info(bvid: str):
    service = VideoService()
    info = service.fetch_info_with_tags(bvid)
    print(f"标题：{info.title}")
    print(f"UP主：{info.owner.name}（mid={info.owner.mid}）")
    print(f"播放/弹幕/评论：{info.stat.num_view}/{info.stat.num_dm}/{info.stat.num_reply}")
    print(f"标签：{info.tags}")


def cmd_video(bvid: str):
    service = VideoService()
    result = service.download_video_with_audio(bvid)
    print(f"已下载：{result.path}")


def cmd_cover(bvid: str):
    service = VideoService()
    result = service.download_cover(bvid)
    print(f"封面：{result.path}")


def cmd_rank():
    service = RankService()
    bvs = service.get_popular(pn=1, ps=10)
    print(f"热门视频 {len(bvs)} 个：{bvs}")


COMMANDS = {
    "info": cmd_info,
    "video": cmd_video,
    "cover": cmd_cover,
    "rank": cmd_rank,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return
    command = sys.argv[1]
    if command not in COMMANDS:
        print(f"未知命令：{command}\n")
        print(__doc__)
        return
    args = sys.argv[2:]
    COMMANDS[command](*args)


if __name__ == "__main__":
    main()
