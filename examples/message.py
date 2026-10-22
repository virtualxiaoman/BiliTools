"""私信导出示例（只读）。

- 单个会话：导出与指定 mid 的全部历史聊天记录；
- 全部会话：默认导出除系统消息外的全部分组，max_num 限制会话数量；
  groups 可传 session_type 整数（1/2/3/5/6/7/8/9）或常用名称；
- 默认增量同步：已有 messages.json 时只拉取新消息，并同步重写 JSON 和 Markdown；
  force=True 时忽略缓存全量刷新，并重新下载图片。
- 全部导出时每处理完一个会话打印一行进度：已导出 N 个会话 / 共 total 个会话 / X 条消息。

落盘位置：output/message/{我的mid}/{好友mid}/messages.json + messages.md + assets/
"""

from src.services import MessageService


def export_single(mid: int, force: bool = False) -> None:
    """导出与某个用户的全部历史私信。"""
    result = MessageService().export_user_messages(mid, force=force)
    print(
        f"已导出 {result.message_count} 条消息（新增 {result.new_message_count} 条）："
        f"{result.export_dir}"
    )


def export_all(max_num: int = 20, groups=None, force: bool = False) -> None:
    """导出全部私信。

    :param max_num: 最多导出多少个会话；-1 表示不限制
    :param groups: 要导出的分组；None 表示除系统消息外的全部分组
    :param force: 是否忽略已有缓存全量刷新
    """
    result = MessageService().export_all_messages(
        groups=groups, max_num=max_num, force=force
    )
    print(
        f"已导出 {result.conversation_count} 个会话 / {result.message_count} 条消息"
        f"（新增 {result.new_message_count} 条，截断：{result.truncated}）："
        f"{result.export_dir}"
    )
    for error in result.errors:
        print(f"失败：{error}")


if __name__ == "__main__":
    # 按需修改 mid；直接运行会对该会话做增量导出。
    # export_single(249056021, force=True)     # 忽略缓存，全量刷新
    # export_all(max_num=20)                   # 导出最近 20 个会话
    # export_all(groups=[1, 2], max_num=-1)    # 只导出用户/未关注人，全部会话
    # export_single(249056021)
    export_all(max_num=-1)
