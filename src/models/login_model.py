"""
登录相关的数据模型。

- `LoginUser`  登录后的用户信息（来自 nav 接口）
"""

import time
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
    vip_status: int = 0  # 大会员状态（nav 的 vipStatus）
    vip_due_date: int = 0  # 大会员到期时间（毫秒时间戳）

    # 原始响应（便于排查/调试，可按需去掉）
    raw: Optional[dict] = field(default=None, repr=False)

    @property
    def is_vip(self) -> bool:
        """当前是否为有效大会员（以到期时间为准，避免依赖缓存状态位）。"""
        if self.vip_status != 1:
            return False
        if self.vip_due_date <= 0:
            return True
        return self.vip_due_date > int(time.time() * 1000)

    @classmethod
    def from_nav_json(cls, data: dict) -> "LoginUser":
        """从 nav 接口（x/web-interface/nav）的 data 字段构造。"""
        return cls(
            is_login=bool(data.get("isLogin", False)),
            mid=data.get("mid"),
            uname=data.get("uname", ""),
            face=data.get("face", ""),
            level=data.get("level_info", {}).get("current_level", 0) if data.get("level_info") else 0,
            vip_status=int(data.get("vipStatus") or 0),
            vip_due_date=int(data.get("vipDueDate") or 0),
            raw=data,
        )
