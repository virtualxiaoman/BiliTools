"""
路径锚点：全库统一的路径管理。

以 `PROJECT_ROOT` 为基准派生所有路径常量，杜绝依赖当前工作目录(cwd)的裸相对路径。
PyInstaller 打包后（sys.frozen）锚定到可执行文件所在目录，保证 output/assets 可写。

cookie 路径由「模块常量」演进为「运行时 getter + override」：
- 全局 cookie 目录默认 `%APPDATA%\\xiaoman\\BiliTools\\cookie`（可经 `set_cookie_dir` 改到别处）；
- 当前生效的 cookie 文件 = 当前账号的 cookie 路径（`set_cookie_path`），无账号时落在 cookie 目录下。
所有消费方应使用 `get_cookie_dir()/get_cookie_path()/get_qr_image_path()`，而非直接读常量。
"""

import os
import sys
from pathlib import Path
from typing import Optional


def _project_root() -> Path:
    """项目根目录：开发模式取 src/config/path.py 向上三级；打包后取 exe 所在目录（可写）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


# 项目根目录
PROJECT_ROOT = _project_root()

# 资源目录（图标等静态资源；cookie 已迁往用户目录）
ASSETS_DIR = PROJECT_ROOT / "assets"
COOKIE_DIR = ASSETS_DIR / "cookie"  # 旧 cookie 目录（兼容引用，默认不再使用）

# 输出目录（统一输出到项目根下的 output/，按业务再分子目录）
OUTPUT_DIR = PROJECT_ROOT / "output"
VIDEO_OUTPUT_DIR = OUTPUT_DIR / "video"  # 视频/音频下载
HISTORY_OUTPUT_DIR = OUTPUT_DIR / "history"  # 历史记录等表格/数据文件
COLLECTION_OUTPUT_DIR = OUTPUT_DIR / "收藏集"  # 收藏表情包、收藏集与装扮素材下载


# 用户数据目录（%APPDATA%\xiaoman\BiliTools）：多账号映射表与默认 cookie 目录
def _appdata_dir() -> Path:
    raw = os.environ.get("APPDATA")
    return Path(raw) if raw else Path.home() / ".config"  # 非 Windows 回退


APP_DATA_DIR = _appdata_dir() / "xiaoman" / "BiliTools"
COOKIE_ROOT = APP_DATA_DIR / "cookie"  # 全局默认 cookie 目录（C 盘用户目录）
ACCOUNTS_FILE = APP_DATA_DIR / "accounts.json"  # 多账号映射表

# 默认 cookie 与二维码图片路径（默认值来源；实际生效路径走下方 getter）
DEFAULT_COOKIE_PATH = COOKIE_DIR / "qr_login.txt"
DEFAULT_QR_IMAGE_PATH = COOKIE_DIR / "qr_login.png"

# ---- 运行时 override：全局 cookie 目录 / 当前账号 cookie 文件 ----
_cookie_dir_override: Optional[Path] = None
_cookie_path_override: Optional[Path] = None


def _normalize_path(path) -> Optional[Path]:
    """规范化路径；None/空串返回 None（表示复位到默认）。"""
    if path is None:
        return None
    if isinstance(path, str) and not path.strip():
        return None
    return Path(path).expanduser().resolve()


def get_cookie_dir() -> Path:
    """当前生效的 cookie 目录（全局设置；默认 %APPDATA%/xiaoman/BiliTools/cookie）。"""
    return _cookie_dir_override if _cookie_dir_override is not None else COOKIE_ROOT


def get_cookie_path() -> Path:
    """当前生效的 cookie 文件路径（当前账号的 cookie；无账号时落在 cookie 目录下）。"""
    if _cookie_path_override is not None:
        return _cookie_path_override
    return get_cookie_dir() / "qr_login.txt"


def get_qr_image_path() -> Path:
    """当前扫码二维码图片保存路径（跟随 cookie 目录）。"""
    return get_cookie_dir() / "qr_login.png"


def set_cookie_dir(path) -> None:
    """设置全局 cookie 目录（None/空串复位到默认 COOKIE_ROOT）。"""
    global _cookie_dir_override
    _cookie_dir_override = _normalize_path(path)


def set_cookie_path(path) -> None:
    """设置当前生效的 cookie 文件路径（账号切换时调用；None 复位到默认）。"""
    global _cookie_path_override
    _cookie_path_override = _normalize_path(path)


def ensure_dirs() -> None:
    """创建所有需要存在的目录（幂等）。"""
    for directory in (
            ASSETS_DIR, COOKIE_DIR, OUTPUT_DIR, VIDEO_OUTPUT_DIR, HISTORY_OUTPUT_DIR,
            COLLECTION_OUTPUT_DIR, COOKIE_ROOT,
    ):
        directory.mkdir(parents=True, exist_ok=True)
