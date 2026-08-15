"""彩色里程碑日志控件：只读富文本，复制/清空/自动滚动，主题切换重绘。"""
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor, QFont, QFontInfo, QTextCharFormat, QTextCursor, QTextFormat,
)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from frontend.pyside6 import theme
from frontend.pyside6.fonts import log_font
from frontend.pyside6.signals import app_signals


class LogWidget(QWidget):
    """下载日志。只记录里程碑事件（追加式），实时百分比不进来（见任务进度区）。"""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setObjectName("Panel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._messages = []  # [(category, ts_text, text)]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        head = QHBoxLayout()
        title = QLabel("下载日志")
        title.setObjectName("SectionTitle")  # 字体由 theme QSS 控制（粗体、随缩放）
        self.btn_copy = QPushButton("复制全部")
        self.btn_clear = QPushButton("清空")
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.btn_copy)
        head.addWidget(self.btn_clear)
        outer.addLayout(head)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        # 日志字体：系统字体、基准 9pt 不随界面调大（随全局缩放）。
        # 必须用 setFont 设置——QSS 字体不会进入 QPlainTextEdit 的文档默认字体。
        self.text.setFont(log_font())
        self.text.setMaximumBlockCount(max(50, settings.get("log_max_lines", 1000)))
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        outer.addWidget(self.text, 1)

        self.btn_copy.clicked.connect(self.copy_all)
        self.btn_clear.clicked.connect(self.clear_log)
        app_signals.log_message.connect(self.append)
        # 主题/缩放变化时 QSS 会覆盖日志控件字体，需重新 setFont 并重建已有日志行
        app_signals.theme_changed.connect(lambda _n: self._apply_log_font())
        app_signals.zoom_changed.connect(lambda _z: self._apply_log_font())

    def _apply_log_font(self):
        """按当前缩放重设日志字体，并重建已有日志行以应用新字号。"""
        self.text.setFont(log_font())
        self._rebuild()

    # ---- 日志写入 ----

    def append(self, category, text):
        category = int(category)
        ts = ""
        if self.settings.get("log_timestamp", True):
            ts = time.strftime("[%H:%M:%S] ")
        self._messages.append((category, ts, text))
        max_lines = max(50, self.settings.get("log_max_lines", 1000))
        if len(self._messages) > max_lines:
            self._messages = self._messages[-max_lines:]
        self._insert_line(category, ts + text)

    def _insert_line(self, category, line):
        color, bold = theme.log_colors(category)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        # 显式指定日志字体：覆盖光标处继承的 QSS 像素字号，
        # 避免被文档/控件/应用字体传播影响（系统字体 + 缩放后的字号）
        font = log_font()
        fmt.setFont(font)
        fmt.setProperty(QTextFormat.Property.FontPixelSize, QFontInfo(font).pixelSize())
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        cursor = self.text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(line + "\n", fmt)
        self.text.setTextCursor(cursor)
        self.text.ensureCursorVisible()

    def _rebuild(self):
        self.text.clear()
        for category, ts, text in self._messages:
            self._insert_line(category, ts + text)

    # ---- 操作 ----

    def copy_all(self):
        self.text.selectAll()
        self.text.copy()
        cursor = self.text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.text.setTextCursor(cursor)

    def clear_log(self):
        self.text.clear()
        self._messages = []
