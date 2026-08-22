"""用户信息示例。"""

from src.services import UserService


MID = 3493265644980448  # 原 quick_start.py 中的 UP 主示例


def get_user_info() -> None:
    """获取 UP 主昵称、粉丝数和等级。"""
    info = UserService().fetch_info(MID)
    print(f"昵称：{info.name}")
    print(f"mid：{info.mid}")
    print(f"粉丝：{info.num_follower}")
    print(f"等级：{info.level}")


if __name__ == "__main__":
    get_user_info()
