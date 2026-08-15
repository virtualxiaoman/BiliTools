"""自定义标题栏：软件名 + 主题切换 + 最小化/最大化/关闭，支持拖拽移动。

窗口操作与主题切换用 SVG 图标（assets/imgs/svg/），Qt 的 SVG 渲染器不支持
currentColor（会渲染成黑色），因此运行时把 fill 替换成当前主题的前景色再渲染，
并在切换主题时重建图标。
"""
from functools import lru_cache

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from src import __version__
from src.config.path import ASSETS_DIR

from frontend.pyside6.signals import app_signals
from frontend.pyside6.theme import current_theme, get_palette

_SVG_DIR = ASSETS_DIR / "imgs" / "svg"
_ICON_SIZE = QSize(16, 16)
# 主题切换按钮：浅色显示月亮（点击转深色），深色显示太阳（点击转浅色）
_THEME_ICON = {"light": "moon", "dark": "sun"}


@lru_cache(maxsize=None)
def _svg_icon(name: str, color: str) -> QIcon:
    """把 SVG 的 currentColor 替换为指定颜色后渲染为 QIcon。

    :param name: SVG 文件名（不含扩展名），如 "close"
    :param color: 替换 currentColor 的 hex 颜色，如 "#212121"
    """
    path = _SVG_DIR / f"{name}.svg"
    if not path.exists():
        return QIcon()
    data = path.read_text(encoding="utf-8").replace("currentColor", color)
    pm = QPixmap()
    return QIcon(pm) if pm.loadFromData(data.encode("utf-8")) else QIcon()


class TitleBar(QWidget):
    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()
    theme_toggled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(40)
        self._drag_offset = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 8, 0)
        lay.setSpacing(2)

        self.title = QLabel(f"BiliTools V{__version__}")
        self.title.setObjectName("AppTitle")  # 字体由 theme QSS 控制（粗体、随缩放）
        lay.addWidget(self.title)
        lay.addStretch(1)

        # 运行中任务数：浮层居中显示在标题栏内（必须传 parent，否则会成为独立顶层窗口），
        # 不参与布局、不拦截鼠标
        self.count_label = QLabel(self)
        self.count_label.setObjectName("Dim")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.count_label.hide()

        self.btn_theme = self._btn("🌙", "切换深浅色主题")
        self.btn_min = self._btn("—", "最小化")
        self.btn_max = self._btn("□", "最大化 / 还原")
        self.btn_close = self._btn("✕", "关闭")
        self.btn_close.setObjectName("TitleBtnClose")

        for b in (self.btn_theme, self.btn_min, self.btn_max, self.btn_close):
            lay.addWidget(b)

        self.btn_theme.clicked.connect(self.theme_toggled)
        self.btn_min.clicked.connect(self.minimize_requested)
        self.btn_max.clicked.connect(self.maximize_requested)
        self.btn_close.clicked.connect(self.close_requested)

        # 图标颜色 / 主题按钮图标随主题切换更新
        app_signals.theme_changed.connect(self._on_theme_changed)
        self._apply_theme_icons()

    def set_task_count(self, n):
        if n and n > 0:
            self.count_label.setText(f"运行中 {n}")
            self.count_label.show()
        else:
            self.count_label.setText("")
            self.count_label.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 让数量提示铺满标题栏，靠 AlignCenter 居中
        self.count_label.setGeometry(0, 0, self.width(), self.height())

    def _btn(self, fallback_text, tip):
        """窗口按钮：优先用 SVG 图标，加载失败时退回文本。"""
        b = QPushButton(fallback_text)
        b.setObjectName("TitleBtn")
        b.setFixedSize(34, 28)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def _set_icon(self, button, icon_name, fallback_text):
        """给按钮设置当前主题前景色的 SVG 图标（失败则回退到文本）。"""
        icon = _svg_icon(icon_name, get_palette()["text"])
        if icon.isNull():
            button.setIcon(QIcon())
            button.setText(fallback_text)
        else:
            button.setIcon(icon)
            button.setIconSize(_ICON_SIZE)
            button.setText("")

    def _apply_theme_icons(self):
        """按当前主题刷新图标：窗口按钮换前景色，主题按钮在 月亮/太阳 间切换。"""
        self._set_icon(self.btn_theme, _THEME_ICON[current_theme()], "🌙")
        self._set_icon(self.btn_min, "minimize", "—")
        self._set_icon(self.btn_max, "maximize", "□")
        self._set_icon(self.btn_close, "close", "✕")

    def _on_theme_changed(self, _name):
        self._apply_theme_icons()

    # ---- 拖拽移动 / 双击最大化 ----

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def mouseDoubleClickEvent(self, event):
        self.maximize_requested.emit()
