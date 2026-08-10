"""
BiliTools 配置包

本包拆分自旧的 `src/config.py`，按职责划分为：
- `path.py`      路径锚点：PROJECT_ROOT 等，全库统一从这里派生路径
- `constants.py` 静态常量：基础域名、User-Agent、重试参数等
- `cookie.py`    Cookie 模型：读取、解析、缓存（原 BiliCookies）

旧的 `src/config.py` 已删除。旧模块（如 `from src.config import Config, BiliCookies, UserAgent`）
通过 `legacy_shim.py` 提供兼容导入，方便过渡期迁移。
"""

from src.config.legacy_shim import Config
from src.config.constants import UserAgent
from src.config.cookie import BiliCookies
from src.config.path import (
    PROJECT_ROOT,
    ASSETS_DIR,
    COOKIE_DIR,
    OUTPUT_DIR,
    VIDEO_OUTPUT_DIR,
    HISTORY_OUTPUT_DIR,
    DEFAULT_COOKIE_PATH,
    QR_IMAGE_PATH,
    ensure_dirs,
)

__all__ = [
    "Config",
    "UserAgent",
    "BiliCookies",
    "PROJECT_ROOT",
    "ASSETS_DIR",
    "COOKIE_DIR",
    "OUTPUT_DIR",
    "VIDEO_OUTPUT_DIR",
    "HISTORY_OUTPUT_DIR",
    "DEFAULT_COOKIE_PATH",
    "QR_IMAGE_PATH",
    "ensure_dirs",
]
