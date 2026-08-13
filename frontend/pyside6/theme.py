"""深色/浅色主题：调色板 token + QSS 生成 + 日志语义色。

样式设计参考 `frontend/old/config.py`：
- 主强调色：天依蓝 #66CCFF；
- 按钮：圆角 + 彩色边框 + hover/pressed 变体（阿洛娜风格）；
- 输入框：圆角 + hover 变红；
- 深浅两套由同一 QSS 模板 + token 生成，全应用统一，不依赖系统观感。
"""
from PySide6.QtWidgets import QApplication

from frontend.pyside6.signals import LogCategory

CURRENT_THEME = "light"

# 调色板 token：浅色 / 深色各一组
_PALETTES = {
    "light": {
        "bg": "#f3f5f8",
        "panel_bg": "#ffffff",
        "card_bg": "#f7f9fb",
        "border": "#d5dbe3",
        "text": "#212121",
        "text_dim": "#8a94a3",
        "accent": "#66CCFF",
        "accent_hover": "#8fdaff",
        "accent_focus": "#3fb1e8",
        "input_bg": "#ffffff",
        "input_border": "#cfd8e3",
        "input_hover_border": "#e54d6b",
        "btn_bg": "#eef2f6",
        "btn_hover": "#dce8f2",
        "btn_pressed": "#cfe0ee",
        "btn_border": "#c6d2de",
        "btn_text": "#333c47",
        "btn_primary_text": "#12303f",
        "titlebar_bg": "#ffffff",
        "titlebar_hover": "#e4e9ef",
        "nav_bg": "#ffffff",
        "nav_text": "#5b6572",
        "nav_active": "#0a86c9",
        "progress_bg": "#e4e9ef",
        "progress_fg": "#3fb1e8",
        "scroll_handle": "#c2ccd8",
        "scroll_bg": "transparent",
    },
    "dark": {
        "bg": "#1e1e1e",
        "panel_bg": "#26272b",
        "card_bg": "#2d2f34",
        "border": "#3f4147",
        "text": "#e0e0e0",
        "text_dim": "#8a8a93",
        "accent": "#66CCFF",
        "accent_hover": "#8fdaff",
        "accent_focus": "#7fd4f0",
        "input_bg": "#2d2f34",
        "input_border": "#484a52",
        "input_hover_border": "#e54d6b",
        "btn_bg": "#33353b",
        "btn_hover": "#3d4048",
        "btn_pressed": "#484b54",
        "btn_border": "#4a4d55",
        "btn_text": "#e0e0e0",
        "btn_primary_text": "#12303f",
        "titlebar_bg": "#26272b",
        "titlebar_hover": "#3a3d44",
        "nav_bg": "#26272b",
        "nav_text": "#9aa1ab",
        "nav_active": "#66CCFF",
        "progress_bg": "#3a3d44",
        "progress_fg": "#66CCFF",
        "scroll_handle": "#55585f",
        "scroll_bg": "transparent",
    },
}

# 日志语义色（深色模式提高亮度保证可读性；普通信息用主题前景色）
_LOG_COLORS = {
    "light": {
        LogCategory.NORMAL: ("#212121", False),
        LogCategory.PROGRESS: ("#1a4f8b", False),
        LogCategory.WARN: ("#b35c00", False),
        LogCategory.ERROR: ("#c62828", True),
        LogCategory.SUCCESS: ("#2e7d32", True),
    },
    "dark": {
        LogCategory.NORMAL: ("#e0e0e0", False),
        LogCategory.PROGRESS: ("#7fb3e8", False),
        LogCategory.WARN: ("#e59a3d", False),
        LogCategory.ERROR: ("#ff6b6b", True),
        LogCategory.SUCCESS: ("#6fd17a", True),
    },
}


def set_theme(name: str) -> None:
    global CURRENT_THEME
    CURRENT_THEME = "dark" if name == "dark" else "light"


def current_theme() -> str:
    return CURRENT_THEME


def get_palette() -> dict:
    return _PALETTES[CURRENT_THEME]


def log_colors(category: int):
    """返回 (颜色hex, 是否加粗) for a log category under the current theme."""
    return _LOG_COLORS[CURRENT_THEME].get(category, _LOG_COLORS[CURRENT_THEME][LogCategory.NORMAL])


def build_qss(p: dict) -> str:
    """由调色板 token 生成整应用 QSS。"""
    return f"""
QWidget {{ background-color: {p['bg']}; color: {p['text']}; font-size: 13px; }}
QWidget#TitleBar {{ background-color: {p['titlebar_bg']}; border-bottom: 1px solid {p['border']}; }}
QWidget#NavBar {{ background-color: {p['nav_bg']}; border-bottom: 1px solid {p['border']}; }}
QWidget#Panel {{ background-color: {p['panel_bg']}; border: 1px solid {p['border']}; border-radius: 8px; }}
QWidget#Card {{ background-color: {p['card_bg']}; border: 1px solid {p['border']}; border-radius: 8px; }}

QLabel {{ color: {p['text']}; background: transparent; }}
QLabel#Dim {{ color: {p['text_dim']}; }}
QLabel#Hint {{ color: {p['text_dim']}; font-size: 12px; }}

QPushButton {{
    background-color: {p['btn_bg']}; border: 1px solid {p['btn_border']};
    border-radius: 6px; padding: 5px 14px; color: {p['btn_text']};
}}
QPushButton:hover {{ background-color: {p['btn_hover']}; }}
QPushButton:pressed {{ background-color: {p['btn_pressed']}; }}
QPushButton:disabled {{ color: {p['text_dim']}; background-color: {p['bg']}; border-color: {p['border']}; }}
QPushButton#Primary {{
    background-color: {p['accent']}; color: {p['btn_primary_text']};
    border: none; border-radius: 6px; padding: 8px 0; font-weight: 600; font-size: 14px;
}}
QPushButton#Primary:hover {{ background-color: {p['accent_hover']}; }}
QPushButton#Primary:pressed {{ background-color: {p['accent_focus']}; }}
QPushButton#Primary:disabled {{ background-color: {p['progress_bg']}; color: {p['text_dim']}; }}

QPushButton#NavItem {{
    text-align: left; padding: 10px 14px; border-radius: 6px;
    background: transparent; border: none; color: {p['nav_text']}; font-size: 13px;
}}
QPushButton#NavItem:hover {{ background-color: {p['btn_hover']}; }}
QPushButton#NavItem:checked {{
    background-color: {p['accent']}; color: {p['btn_primary_text']}; font-weight: 600;
}}

QPushButton#TitleBtn {{
    background: transparent; border: none; border-radius: 4px;
    color: {p['text']}; font-size: 14px; padding: 0;
}}
QPushButton#TitleBtn:hover {{ background-color: {p['titlebar_hover']}; }}
QPushButton#TitleBtnClose:hover {{ background-color: #e81123; color: #ffffff; }}

QLineEdit {{
    background-color: {p['input_bg']}; border: 1px solid {p['input_border']};
    border-radius: 4px; padding: 5px 8px; color: {p['text']};
    selection-background-color: {p['accent']}; selection-color: {p['btn_primary_text']};
}}
QLineEdit:hover {{ border-color: {p['input_hover_border']}; }}
QLineEdit:focus {{ border: 1px solid {p['accent']}; }}

QComboBox {{
    background-color: {p['input_bg']}; border: 1px solid {p['input_border']};
    border-radius: 4px; padding: 3px 8px; color: {p['text']}; min-height: 18px;
}}
QComboBox:hover {{ border-color: {p['input_hover_border']}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background-color: {p['panel_bg']}; color: {p['text']};
    border: 1px solid {p['border']}; selection-background-color: {p['accent']};
    selection-color: {p['btn_primary_text']};
}}

QSpinBox {{
    background-color: {p['input_bg']}; border: 1px solid {p['input_border']};
    border-radius: 4px; padding: 2px 6px; color: {p['text']};
}}

QTabBar::tab {{
    background: transparent; color: {p['nav_text']};
    padding: 8px 16px; border-bottom: 2px solid transparent; font-size: 13px;
}}
QTabBar::tab:selected {{ color: {p['nav_active']}; border-bottom: 2px solid {p['nav_active']}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {p['accent_hover']}; }}
QTabWidget::pane {{ border: none; }}

QRadioButton {{ color: {p['text']}; background: transparent; spacing: 6px; }}
QRadioButton::indicator {{
    width: 14px; height: 14px; border-radius: 7px;
    border: 2px solid {p['border']}; background-color: {p['input_bg']};
}}
QRadioButton::indicator:hover {{ border-color: {p['accent']}; }}
QRadioButton::indicator:checked {{ border-color: {p['accent']}; background-color: {p['accent']}; }}

QProgressBar {{
    background-color: {p['progress_bg']}; border: none; border-radius: 4px;
    text-align: center; color: {p['text']}; min-height: 10px;
}}
QProgressBar::chunk {{ background-color: {p['progress_fg']}; border-radius: 4px; }}

QPlainTextEdit {{
    background-color: {p['panel_bg']}; border: 1px solid {p['border']};
    border-radius: 4px; color: {p['text']};
    selection-background-color: {p['accent']}; selection-color: {p['btn_primary_text']};
}}
QScrollBar:vertical {{ background: {p['scroll_bg']}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p['scroll_handle']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {p['scroll_bg']}; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {p['scroll_handle']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QToolTip {{ background-color: {p['panel_bg']}; color: {p['text']}; border: 1px solid {p['border']}; padding: 4px; }}
QMenu {{ background-color: {p['panel_bg']}; color: {p['text']}; border: 1px solid {p['border']}; }}
QMenu::item {{ padding: 6px 20px; }}
QMenu::item:selected {{ background-color: {p['accent']}; color: {p['btn_primary_text']}; }}
QGroupBox {{ border: 1px solid {p['border']}; border-radius: 6px; margin-top: 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {p['text_dim']}; }}
"""


class ThemeManager:
    """主题控制器：负责切换主题并整应用应用 QSS。"""

    def __init__(self, settings):
        self.settings = settings
        set_theme(self.settings.get("theme", "light"))

    def current(self) -> str:
        return CURRENT_THEME

    def apply(self, app: QApplication) -> None:
        app.setStyleSheet(build_qss(get_palette()))

    def set_theme(self, name: str) -> None:
        set_theme(name)
        self.settings.set("theme", CURRENT_THEME)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_qss(get_palette()))
        # 通知依赖语义色的控件（如日志）重建着色
        from frontend.pyside6.signals import app_signals
        app_signals.theme_changed.emit(CURRENT_THEME)
