"""
用户（UP主/自己）相关的数据模型。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UserInfo:
    """用户信息（原 BiliUserInfo 返回数据的主体）。

    :param mid: 用户UID
    :param name: 昵称
    :param face: 头像
    :param sign: 个性签名
    :param num_following: 关注数
    :param num_follower: 粉丝数
    :param level: 等级
    """

    mid: int = 0
    name: str = ""  # 昵称
    face: str = ""  # 头像
    sign: str = ""  # 个性签名
    num_following: int = 0  # 关注数
    num_follower: int = 0  # 粉丝数
    level: int = 0  # 等级

    # 原始响应（便于排查/调试，可按需去掉）
    raw: Optional[dict] = field(default=None, repr=False)

    @classmethod
    def from_card_json(cls, data: dict) -> "UserInfo":
        """从用户卡片接口（x/web-interface/card）的 data 字段构造。

        :param data: card 接口返回的 data 字典
        """
        card = data.get("card") or {}
        level_info = card.get("level_info") or {}
        return cls(
            mid=data.get("mid", 0) or card.get("mid", 0),
            name=card.get("name", ""),
            face=card.get("face", ""),
            sign=card.get("sign", ""),
            num_following=card.get("attention", 0),
            num_follower=card.get("fans", 0) or data.get("follower", 0),
            level=level_info.get("current_level", 0),
            raw=data,
        )
