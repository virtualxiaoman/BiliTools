"""
兼容层：让旧代码 `from src.config import Config, BiliCookies, UserAgent` 继续可用。

仅供迁移过渡期使用，新代码应直接导入：
    from src.config.constants import UserAgent, MAX_RETRY, ...
    from src.config.cookie import BiliCookies
    from src.config.path import DEFAULT_COOKIE_PATH
"""

from src.config.constants import UserAgent
from src.config.cookie import BiliCookies
from src.config.path import DEFAULT_COOKIE_PATH


class Config:
    """旧 Config 的兼容占位：路径相关常量改为引用新 path 模块。

    注意：旧代码 `Config.COOKIE_PATH` 指向相对路径 "./assets/cookie/qr_login.txt"，
    现在统一为基于 PROJECT_ROOT 的绝对路径 DEFAULT_COOKIE_PATH。
    """

    COOKIE_PATH = DEFAULT_COOKIE_PATH
    # LOGIN_QR_PATH = "./assets/cookie/qr_login.png"
    MAX_RETRY = 3  # 最大重试次数3次
    RETRY_DELAY = 0.712  # 重试延迟0.712秒
