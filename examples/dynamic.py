"""动态（opus）下载示例。

解析与下载均为只读操作；默认只演示解析，下载需要手动调用
（会真实请求 B 站并写入 output/dynamic/）。

[运行]
    python -m examples.dynamic
"""

from src.services import DynamicService


# 示例动态：洛天依 2026 巡演（图文 + 互动抽奖 + 内联表情）
DYNAMIC = "https://www.bilibili.com/opus/1250464970768908294"


def show_detail() -> None:
    """解析一条动态（不下载），查看类型/正文/媒体/卡片/抽奖等结构。"""
    service = DynamicService()
    info = service.fetch_detail(DYNAMIC, full_content=True)

    print(f"[{info.kind}] {info.author.name} ({info.author.mid}) ｜ {info.author.pub_time}")
    print(f"原文：{info.url}")
    print(f"数据：点赞 {info.stats.like} · 评论 {info.stats.comment} · 转发 {info.stats.forward}")
    print(f"正文：{info.content.text[:80]!r}…")
    print(f"图片：{[(i.index, i.width, i.height) for i in info.images]}")
    print(f"表情：{[(e.short_name, e.package_id) for e in info.emojis]}")
    print(f"卡片：{[(c.kind, c.title) for c in info.cards]}")
    if info.lottery_rid:
        print(f"互动抽奖：rid={info.lottery_rid}")
    if info.forward is not None:
        print(f"转发：orig_id={info.forward.orig_id} deleted={info.forward.deleted}")


def download_one() -> None:
    """下载一条动态（默认 20 条热评存档 + 转发递归）。"""
    service = DynamicService()
    result = service.download_dynamic(DYNAMIC)
    print(f"保存目录：{result.path}（cached={result.cached}）")
    print(f"媒体文件：{len(result.media)} 个，失败 {len(result.failures)} 个")
    if result.comments_path:
        print(f"评论存档：{result.comments_path}")
    for warning in result.warnings:
        print(f"[警告] {warning}")


def download_without_comments() -> None:
    """关闭评论、强制重下。"""
    service = DynamicService()
    result = service.download_dynamic(
        DYNAMIC, force=True, with_comments=False, comment_max_count=0
    )
    print(f"重下完成：{result.path}")


def download_user_all(mid: int = 36081646, max_count: int = 5) -> None:
    """下载某个 UP 主的全部动态（mid 必要参数；示例默认只取最新 5 条，避免大量请求）。

    可选参数：max_count（-1 全部）、since（YYYY-MM-DD 起）、force、
    with_comments / comment_max_count / comment_sort、max_forward_depth、
    page_interval（爬取节流）、refresh_list（忽略列表快照完整重爬）、
    threads（并发数）、account_sessions（多账号分流）、progress / progress_cb。

    多账号分流示例：
        sessions = [BiliSession(cookie_path="account-a.txt"), BiliSession(cookie_path="account-b.txt")]
        service.download_user_dynamics(mid, threads=2, account_sessions=sessions)
    """
    service = DynamicService()
    results = service.download_user_dynamics(
        mid,
        max_count=max_count,
        with_comments=False,  # 大批量建议关闭评论，降低 API 请求量
    )
    ok = sum(1 for result in results if not result.failures)
    print(f"完成 {len(results)} 条：成功 {ok}，存在失败 {len(results) - ok}")
    for result in results:
        state = "缓存" if result.cached else ("失败" if result.failures else "新下载")
        print(f"  [{state}] {result.path}")


if __name__ == "__main__":
    show_detail()
    print("\n如需下载，调用 download_one() / download_without_comments() / download_user_all()。")
