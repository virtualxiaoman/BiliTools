"""BiliTools 命令行入口（简洁版）。

用法：
    python main.py <command> [args]

可用命令（示例）：
    info      BV号                  获取视频信息
    comments  BV号 [排序] [条数] [--sub]  获取视频评论（--sub 含全部楼中楼；条数默认 -1）
    export-comments BV号 [排序] [条数] [--no-sub]  导出评论 JSON+Markdown（默认含楼中楼）
    dynamic-comments 动态ID/opus链接 [排序] [条数] [--sub]  获取动态评论
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


def _parse_comment_args(
    args: tuple[str, ...], command: str
) -> tuple[str, str, int, bool]:
    """解析 ``<ID> [排序] [条数] [--sub]``，返回目标、排序、条数、是否抓楼中楼。"""
    unknown = [arg for arg in args if arg.startswith("--") and arg != "--sub"]
    if unknown:
        raise ValueError(f"未知参数：{unknown[0]}")

    with_sub_replies = "--sub" in args
    positional = [arg for arg in args if arg != "--sub"]
    if not positional or len(positional) > 3:
        raise ValueError(
            f"用法：{command} <ID> [排序] [条数] [--sub]"
        )

    sort = positional[1] if len(positional) > 1 else "latest"
    try:
        count = int(positional[2]) if len(positional) > 2 else -1
    except ValueError as exc:
        raise ValueError("评论条数必须是整数，-1 表示不限制") from exc
    return positional[0], sort, count, with_sub_replies


def _print_comments(comments: list[dict], with_sub_replies: bool) -> None:
    sub_total = 0
    for comment in comments:
        member = comment.get("member") or {}
        content = comment.get("content") or {}
        print(f"[{member.get('uname', '未知用户')}] {content.get('message', '')}")
        if not with_sub_replies:
            continue
        replies = comment.get("replies") or []
        sub_total += len(replies)
        for reply in replies:
            r_member = reply.get("member") or {}
            r_content = reply.get("content") or {}
            print(
                f"  - [{r_member.get('uname', '未知用户')}] "
                f"{r_content.get('message', '')}"
            )

    if with_sub_replies:
        print(f"共获取 {len(comments)} 条根评论，{sub_total} 条楼中楼")
    else:
        print(f"共获取 {len(comments)} 条评论")


def cmd_comments(*args: str):
    """获取并打印视频评论；max_count=-1 表示不限制，--sub 抓取全部楼中楼。"""
    bvid, sort, count, with_sub_replies = _parse_comment_args(args, "comments")
    comments = ReplyService().get_video_comments(
        bvid=bvid,
        sort=sort,
        max_count=count,
        with_sub_replies=with_sub_replies,
    )
    _print_comments(comments, with_sub_replies)


def cmd_export_comments(*args: str):
    """抓取并导出视频评论（JSON + Markdown），默认包含全部楼中楼。"""
    if "--sub" in args and "--no-sub" in args:
        raise ValueError("--sub 与 --no-sub 不能同时使用")
    with_sub_replies = "--no-sub" not in args
    args = tuple(arg for arg in args if arg not in ("--sub", "--no-sub"))

    bvid, sort, count, _ = _parse_comment_args(args, "export-comments")
    result = ReplyService().export_video_comments(
        bvid=bvid,
        sort=sort,
        max_count=count,
        with_sub_replies=with_sub_replies,
    )
    print(f"JSON：{result.json_path}")
    print(f"Markdown：{result.markdown_path}")
    print(
        f"根评论 {result.root_count} 条（置顶 {result.pinned_count} 条），"
        f"楼中楼 {result.sub_count} 条"
    )


def cmd_dynamic_comments(*args: str):
    """获取并打印动态评论；支持动态 ID 或 bilibili.com/opus/<id> 链接。"""
    dynamic_id, sort, count, with_sub_replies = _parse_comment_args(
        args, "dynamic-comments"
    )
    comments = ReplyService().get_dynamic_comments(
        dynamic_id=dynamic_id,
        sort=sort,
        max_count=count,
        with_sub_replies=with_sub_replies,
    )
    _print_comments(comments, with_sub_replies)


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
    "export-comments": cmd_export_comments,
    "dynamic-comments": cmd_dynamic_comments,
    "summary": cmd_summary,
    "video": cmd_video,
    "cover": cmd_cover,
    "rank": cmd_rank,
}


def main():
    # Windows 控制台默认 GBK，评论里的表情/生僻字无法编码；替换而不是中断输出。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

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
