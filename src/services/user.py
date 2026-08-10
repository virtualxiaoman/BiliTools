"""
用户（UP主）服务：用户信息、老粉签约。

- `UserService`     用户公开信息（对应旧 BiliUserInfo）
- `ContractService` 老粉契约（对应旧 BiliContract）

说明：旧 `BiliUserInfo` 中针对 space/wbi/acc/info 接口的风控参数（dm_img_*、w_webid 等）
是容易过期且依赖抓包的参数，这里改为主用无需风控参数的 `/x/space/acc/info` 与 `/x/web-interface/card`。
"""

import logging
from typing import Optional

from src.api.session import BiliSession
from src.models.user import UserInfo
from src.urls.user import UserUrls
from src.urls.contract import ContractUrls

logger = logging.getLogger(__name__)


class UserService:
    """B 站用户信息服务。"""

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    def fetch_info(self, mid: int) -> UserInfo:
        """获取用户公开信息（昵称/头像/签名/粉丝数等）。

        使用用户卡片接口（x/web-interface/card，数据较全且无需 wbi 签名）。
        （旧实现用的 /x/space/wbi/acc/info 需要 dm_img_* 等易过期的风控参数，已弃用。）

        :param mid: 用户UID
        :return: UserInfo
        """
        data = self.session.get(UserUrls.CARD, params={"mid": mid})
        return UserInfo.from_card_json(data)

    def get_name(self, mid: int) -> Optional[str]:
        """获取用户昵称，获取失败返回 None。"""
        try:
            return self.fetch_info(mid).name
        except Exception as e:
            logger.warning("[UserService] 获取用户 %s 昵称失败：%s", mid, e)
            return None

    def fetch_card(self, mid: int) -> dict:
        """获取用户卡片信息（含粉丝数/关注状态/投稿数等，接口返回较全）。

        :param mid: 用户UID
        :return: card 接口的 data 字典
        """
        return self.session.get(UserUrls.CARD, params={"mid": mid})


class ContractService:
    """老粉/契约服务。"""

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    def add_contract(self, up_mid: int) -> bool:
        """执行签约请求，成为 UP 主的老粉。

        :param up_mid: 目标UP主的UID
        :return: 是否成功
        """
        from src.config.cookie import BiliCookies

        csrf = BiliCookies.from_file().bili_jct or ""
        payload = {
            "aid": "",
            "up_mid": up_mid,
            "source": "4",
            "scene": "105",
            "platform": "web",
            "mobi_app": "pc",
            "csrf": csrf,
        }
        data = self.session.post(ContractUrls.ADD_CONTRACT, data=payload)
        logger.info("[ContractService] 签约请求返回：%s", data)
        return True
