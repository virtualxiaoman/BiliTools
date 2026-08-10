"""
登录相关的数据模型。

- `LoginUser`  登录后的用户信息（来自 nav 接口）
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LoginUser:
    """登录状态与当前登录用户信息。"""

    is_login: bool = False  # 是否已登录
    mid: Optional[int] = None  # 用户UID
    uname: str = ""  # 用户名
    face: str = ""  # 头像
    level: int = 0  # 等级

    # 原始响应（便于排查/调试，可按需去掉）
    raw: Optional[dict] = field(default=None, repr=False)

    @classmethod
    def from_nav_json(cls, data: dict) -> "LoginUser":
        """从 nav 接口（x/web-interface/nav）的 data 字段构造。"""
        return cls(
            is_login=bool(data.get("isLogin", False)),
            mid=data.get("mid"),
            uname=data.get("uname", ""),
            face=data.get("face", ""),
            level=data.get("level_info", {}).get("current_level", 0) if data.get("level_info") else 0,
            raw=data,
        )
