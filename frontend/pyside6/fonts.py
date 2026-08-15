"""界面字体：优先使用方正兰亭圆（常规/粗），缺失时回退系统字体。

- 常规字体 `FZLanTYK_Zhong.c10069d1.OTF`（族名 FZLanTingYuanGBK）作为应用默认字体；
- 粗体 `FZLanTYJW_Cu.TTF`（族名 FZLanTingYuanS-B-GB）用于标题/强调文字；
- 下载日志内容保持系统字体、基准字号不随界面调大，由 theme 的 QPlainTextEdit 规则控制。

两个文件是不同族名，Qt 不会按 font-weight 跨族匹配，因此粗体元素需显式指定
font-family（theme.build_qss 注入 / 控件 setFont）。

zoom：全局界面缩放系数（0.8~1.6）。应用到默认字体与 QSS 全部 px 尺寸，
由设置页「界面」里的缩放滑块控制。
"""
import logging
from typing import Optional

from PySide6.QtGui import QFont, QFontDatabase

from src.config.path import ASSETS_DIR

logger = logging.getLogger(__name__)

FONT_REGULAR_PATH = ASSETS_DIR / "fonts" / "FZLanTYK_Zhong.c10069d1.OTF"
FONT_BOLD_PATH = ASSETS_DIR / "fonts" / "FZLanTYJW_Cu.TTF"
_SYSTEM_FAMILY = "Microsoft YaHei UI"  # 回退用的系统字体

regular_family: Optional[str] = None
bold_family: Optional[str] = None

# 全局界面缩放系数：基准为 1.0，越大界面整体放大
_zoom: float = 1.0


def set_zoom(z: float) -> None:
    """设置全局缩放系数（设置页「界面」滑块调用）。"""
    global _zoom
    _zoom = float(z)


def zoom() -> float:
    return _zoom


def load_fonts() -> None:
    """注册自定义字体（需在 QApplication 创建后调用）。"""
    global regular_family, bold_family
    regular_family = _register(FONT_REGULAR_PATH)
    bold_family = _register(FONT_BOLD_PATH)
    if regular_family or bold_family:
        logger.info("界面字体已加载：常规=%s 粗体=%s", regular_family, bold_family)


def _register(path) -> Optional[str]:
    if not path.exists():
        logger.warning("字体文件缺失，使用系统字体：%s", path)
        return None
    fid = QFontDatabase.addApplicationFont(str(path))
    if fid < 0:
        logger.warning("字体加载失败，使用系统字体：%s", path)
        return None
    families = QFontDatabase.applicationFontFamilies(fid)
    return families[0] if families else None


def app_font() -> QFont:
    """应用默认字体：常规兰亭圆，缺失则回退系统字体。基准 12pt，随缩放放大。"""
    f = QFont(regular_family or _SYSTEM_FAMILY)
    f.setPointSizeF(12 * _zoom)
    return f


def bold_font(size: int = 13) -> QFont:
    """标题/强调字体：粗体兰亭圆，缺失则回退系统加粗。随缩放放大。"""
    f = QFont(bold_family or _SYSTEM_FAMILY)
    f.setPointSizeF(size * _zoom)
    if not bold_family:
        f.setWeight(QFont.Weight.Bold)
    return f


def log_font() -> QFont:
    """下载日志内容字体：系统字体，基准 11pt（随全局缩放）。

    日志内容必须用代码 setFont 设置（QSS 字体不会进入 QPlainTextEdit 的文档默认字体）。
    """
    f = QFont(_SYSTEM_FAMILY)
    f.setPointSizeF(11 * _zoom)
    return f


def bold_family_name() -> Optional[str]:
    """粗体兰亭圆的族名（未加载时为 None，供 QSS / setFont 使用）。"""
    return bold_family


def bold_family_css() -> str:
    """粗体字体的 QSS `font-family: "X"; ` 片段（未加载时为空串）。"""
    return f'font-family: "{bold_family}"; ' if bold_family else ""
