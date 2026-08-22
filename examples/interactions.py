"""评论、私信和老粉签约示例。

以下操作会真实改变账号状态，默认不在 main() 中自动执行。
"""

from src.services import ContractService, MessageService, ReplyService


BVID = "BV1ov42117yC"


def send_reply() -> None:
    """发表评论。"""
    rpid = ReplyService().send_reply("小梓我喜欢你~", bvid=BVID)
    print(f"评论成功，rpid={rpid}")


def send_message() -> None:
    """发送私信。"""
    MessageService().send_msg(
        receiver_uid=3493133776062465,
        content="你好，请问是千年的爱丽丝同学吗？",
    )
    print("私信已发送")


def add_contract() -> None:
    """申请成为 UP 主的老粉。"""
    success = ContractService().add_contract(up_mid=506925078)
    print(f"老粉签约结果：{success}")


if __name__ == "__main__":
    print("这是写操作示例，不会自动发送评论、私信或签约。")
    print("确认账号、内容和目标后，再手动调用对应函数。")
