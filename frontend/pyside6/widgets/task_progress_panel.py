"""实时任务进度区：每个运行中任务一行（描述 + 进度条 + 百分比 + 阶段文本）。

百分比是「覆盖式」就地刷新（QProgressBar.setValue），不产生日志行。
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QScrollArea, QVBoxLayout, QWidget,
)

from frontend.pyside6 import fonts


class TaskRow(QWidget):
    def __init__(self, desc):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.desc = QLabel(desc)
        self.desc.setMinimumWidth(110)
        self.desc.setToolTip(desc)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(150)
        self.pct = QLabel("0%")
        self.pct.setFixedWidth(38)
        self.status = QLabel("")
        self.status.setObjectName("Dim")

        lay.addWidget(self.desc, 1)
        lay.addWidget(self.bar)
        lay.addWidget(self.pct)
        lay.addWidget(self.status)

    def set_progress(self, done, total):
        if total:
            pct = min(int(done / total * 100), 100)
            self.bar.setRange(0, 100)
            self.bar.setValue(pct)
            self.pct.setText(f"{pct}%")
        else:
            # 未知总量：不定态（滚动条）
            self.bar.setRange(0, 0)
            self.pct.setText("—")

    def set_phase(self, text):
        self.status.setText(text)
        self.status.setToolTip(text)
        if "ffmpeg" in text.lower() or "合成" in text:
            self.bar.setRange(0, 0)  # 合成阶段无字节 → 不定态
        else:
            self.bar.setRange(0, 100)

    def set_finished(self, success, summary):
        self.bar.setRange(0, 100)
        self.bar.setValue(100 if success else 0)
        self.pct.setText("✓" if success else "✗")
        self.status.setText(summary[:60])
        self.status.setToolTip(summary)
        color = "#2e7d32" if success else "#c62828"
        self.status.setStyleSheet(f"{fonts.bold_family_css()}color:{color}; font-weight:600;")


class TaskProgressPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.rows_layout = QVBoxLayout(self.container)
        self.rows_layout.setSpacing(4)
        self.rows_layout.addStretch(1)
        self.scroll.setWidget(self.container)
        outer.addWidget(self.scroll)

        self._rows = {}

    def add_task(self, tid, desc):
        if tid in self._rows:
            return
        row = TaskRow(desc)
        self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
        self._rows[tid] = row

    def update_progress(self, tid, done, total):
        row = self._rows.get(tid)
        if row:
            row.set_progress(done, total)

    def set_phase(self, tid, text):
        row = self._rows.get(tid)
        if row:
            row.set_phase(text)

    def finish_task(self, tid, success, summary):
        row = self._rows.get(tid)
        if not row:
            return
        row.set_finished(success, summary)
        QTimer.singleShot(3000, lambda: self._remove(tid))

    def _remove(self, tid):
        row = self._rows.pop(tid, None)
        if row is not None:
            self.rows_layout.removeWidget(row)
            row.deleteLater()
