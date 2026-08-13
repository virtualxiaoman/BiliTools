"""自定义标题栏：软件名 + 主题切换 + 最小化/最大化/关闭，支持拖拽移动。"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


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

        self.title = QLabel("BiliTools")
        self.title.setStyleSheet("font-weight: 600; font-size: 14px;")
        lay.addWidget(self.title)
        lay.addStretch(1)

        # 运行中任务数：浮层居中显示，不参与布局、不拦截鼠标
        self.count_label = QLabel("")
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

    def _btn(self, text, tip):
        b = QPushButton(text)
        b.setObjectName("TitleBtn")
        b.setFixedSize(34, 28)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

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
