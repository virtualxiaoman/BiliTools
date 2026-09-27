"""BiliTools 命令行入口（简洁版）。

用法：
    python main.py <command> [args]

可用命令（示例）：
    info      BV号                  获取视频信息
    comments  BV号 [排序] [条数]    获取视频评论（排序：latest 或 hot；条数默认 -1）
    dynamic-comments 动态ID/opus链接 [排序] [条数]  获取动态评论
    summary   BV号 [cid]              获取视频 AI 总结文本
    video     BV号                  下载视频（含音频）
    cover     BV号                  下载封面
    rank                            获取热门视频

完整示例见 examples/quick_start.py
"""

import sys

from src.services import RankService, ReplyService, VideoService


def cmd_info(bvid: str):
    service = VideoService()
    info = service.fetch_info_with_tags(bvid)
    print(f"标题：{info.title}")
    print(f"UP主：{info.owner.name}（mid={info.owner.mid}）")
    print(f"播放/弹幕/评论：{info.stat.num_view}/{info.stat.num_dm}/{info.stat.num_reply}")
    print(f"标签：{info.tags}")


def cmd_comments(bvid: str, sort: str = "latest", max_count: str = "-1"):
    """获取并打印视频评论；max_count=-1 表示不限制。"""
    try:
        count = int(max_count)
    except ValueError as exc:
        raise ValueError("评论条数必须是整数，-1 表示不限制") from exc

    comments = ReplyService().get_video_comments(
        bvid=bvid, sort=sort, max_count=count
    )
    for comment in comments:
        member = comment.get("member") or {}
        content = comment.get("content") or {}
        uname = member.get("uname", "未知用户")
        message = content.get("message", "")
        print(f"[{uname}] {message}")
    print(f"共获取 {len(comments)} 条评论")


def cmd_dynamic_comments(dynamic_id: str, sort: str = "latest", max_count: str = "-1"):
    """获取并打印动态评论；支持动态 ID 或 bilibili.com/opus/<id> 链接。"""
    try:
        count = int(max_count)
    except ValueError as exc:
        raise ValueError("评论条数必须是整数，-1 表示不限制") from exc

    comments = ReplyService().get_dynamic_comments(
        dynamic_id=dynamic_id, sort=sort, max_count=count
    )
    for comment in comments:
        member = comment.get("member") or {}
        content = comment.get("content") or {}
        uname = member.get("uname", "未知用户")
        message = content.get("message", "")
        print(f"[{uname}] {message}")
    print(f"共获取 {len(comments)} 条评论")


def cmd_summary(bvid: str, cid: str = ""):
    """获取并打印视频 AI 总结文本；未传 cid 时自动使用首个分 P。"""
    service = VideoService()
    if cid:
        try:
            summary = service.get_ai_summary_text(bvid=bvid, cid=int(cid))
        except ValueError as exc:
            raise ValueError("cid 必须是整数") from exc
    else:
        summary = service.get_ai_summary_text(bvid=bvid)
    print(summary)


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
    "comments": cmd_comments,
    "dynamic-comments": cmd_dynamic_comments,
    "summary": cmd_summary,
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
