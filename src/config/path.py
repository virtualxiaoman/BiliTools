"""
路径锚点：全库统一的路径管理。

以 `PROJECT_ROOT` 为基准派生所有路径常量，杜绝依赖当前工作目录(cwd)的裸相对路径。
PyInstaller 打包后（sys.frozen）锚定到可执行文件所在目录，保证 output/assets 可写。
"""

import sys
from pathlib import Path


def _project_root() -> Path:
    """项目根目录：开发模式取 src/config/path.py 向上三级；打包后取 exe 所在目录（可写）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


# 项目根目录
PROJECT_ROOT = _project_root()

# 资源目录（cookie、图标等静态资源）
ASSETS_DIR = PROJECT_ROOT / "assets"
COOKIE_DIR = ASSETS_DIR / "cookie"  # cookie 的唯一存放目录

# 输出目录（统一输出到项目根下的 output/，按业务再分子目录）
OUTPUT_DIR = PROJECT_ROOT / "output"
VIDEO_OUTPUT_DIR = OUTPUT_DIR / "video"  # 视频/音频下载
HISTORY_OUTPUT_DIR = OUTPUT_DIR / "history"  # 历史记录等表格/数据文件

# 默认 cookie 与二维码图片路径
DEFAULT_COOKIE_PATH = COOKIE_DIR / "qr_login.txt"
DEFAULT_QR_IMAGE_PATH = COOKIE_DIR / "qr_login.png"


def ensure_dirs() -> None:
    """创建所有需要存在的目录（幂等）。"""
    for directory in (ASSETS_DIR, COOKIE_DIR, OUTPUT_DIR, VIDEO_OUTPUT_DIR, HISTORY_OUTPUT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
