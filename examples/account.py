"""登录状态和多账号示例。"""

from src.services import LoginService
from src.services.account import AccountManager


def get_login_state() -> None:
    """查看当前 cookie 对应的登录状态。"""
    user = LoginService().get_login_state()
    print(f"是否登录：{user.is_login}")
    print(f"mid：{user.mid}")
    print(f"昵称：{user.uname}")


def list_accounts() -> None:
    """列出本地账号映射。"""
    accounts = AccountManager().list_accounts()
    for account in accounts:
        print(account.as_dict())


def switch_account(mid: int) -> None:
    """切换当前账号；切换后新建的 BiliSession 会使用对应 cookie。"""
    account = AccountManager().switch(mid)
    print(f"当前账号：{account.as_dict() if account else None}")


if __name__ == "__main__":
    get_login_state()
    list_accounts()
