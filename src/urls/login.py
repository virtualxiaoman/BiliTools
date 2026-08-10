"""
登录相关的接口 URL。
原 `src/login.py` 中的 `LoginUrls` 迁移至此。
"""

from src.config.constants import API_BASE, PASSPORT_BASE


class LoginUrls:
    """扫码登录与登录状态查询接口。"""

    LOGIN_STATE = f"{API_BASE}/x/web-interface/nav"  # 登录状态/用户信息（同时也是 wbi keys 来源）
    QR_GENERATE = f"{PASSPORT_BASE}/x/passport-login/web/qrcode/generate"  # 生成二维码
    QR_LOGIN = f"{PASSPORT_BASE}/x/passport-login/web/qrcode/poll"  # 扫码登录轮询
