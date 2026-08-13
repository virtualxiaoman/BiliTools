"""设置页。"""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QRadioButton, QScrollArea, QSpinBox, QVBoxLayout,
    QWidget,
)

from src.config.path import COOKIE_DIR, VIDEO_OUTPUT_DIR
from src.models.download_model import VideoQuality
from src.util.downloader import ffmpeg_available

from ..logs import LOG_DIR


class SettingsPage(QWidget):
    def __init__(self, settings, theme_mgr, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.theme_mgr = theme_mgr

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form = QFormLayout()
        form.setVerticalSpacing(14)

        # 默认保存目录
        self.dir_edit = QLineEdit(settings.get("save_dir"))
        btn_dir = QPushButton("浏览…")
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(btn_dir)
        btn_dir.clicked.connect(self._on_choose_dir)
        form.addRow("默认保存目录", dir_row)

        # 默认清晰度
        self.quality_combo = QComboBox()
        default_q = getattr(VideoQuality, settings.get("quality", "HD4K"), VideoQuality.HD4K)
        for q in VideoQuality:
            self.quality_combo.addItem(q.display_name, q)
        idx = self.quality_combo.findData(default_q)
        self.quality_combo.setCurrentIndex(max(idx, 0))
        self.quality_combo.currentIndexChanged.connect(self._on_quality_changed)
        form.addRow("默认清晰度", self.quality_combo)

        # 默认类型
        self.rb_video = QRadioButton("视频")  # 视频即含声音
        self.rb_audio = QRadioButton("仅音频")
        self.rb_video.setChecked(settings.get("media_type") != "audio")
        self.rb_audio.setChecked(settings.get("media_type") == "audio")
        self.rb_video.toggled.connect(
            lambda on: settings.set("media_type", "video_with_audio") if on else None)
        self.rb_audio.toggled.connect(
            lambda on: settings.set("media_type", "audio") if on else None)
        type_row = QHBoxLayout()
        type_row.addWidget(self.rb_video)
        type_row.addWidget(self.rb_audio)
        type_row.addStretch(1)
        form.addRow("默认类型", type_row)

        # 界面主题
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.setCurrentIndex(0 if settings.get("theme") != "dark" else 1)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        form.addRow("界面主题", self.theme_combo)

        # ffmpeg 检测
        self.ffmpeg_status = QLabel("")
        btn_ffmpeg = QPushButton("检测 ffmpeg")
        btn_ffmpeg.clicked.connect(self._on_check_ffmpeg)
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.addWidget(btn_ffmpeg)
        ffmpeg_row.addWidget(self.ffmpeg_status, 1)
        form.addRow("音视频合成", ffmpeg_row)

        # 日志
        self.lines_spin = QSpinBox()
        self.lines_spin.setRange(100, 100000)
        self.lines_spin.setValue(int(settings.get("log_max_lines", 1000)))
        self.lines_spin.valueChanged.connect(lambda v: settings.set("log_max_lines", v))
        form.addRow("日志最大行数", self.lines_spin)

        self.ts_check = QCheckBox("显示时间戳")
        self.ts_check.setChecked(bool(settings.get("log_timestamp", True)))
        self.ts_check.toggled.connect(lambda on: settings.set("log_timestamp", on))
        form.addRow("日志", self.ts_check)

        # 打开目录
        open_row = QHBoxLayout()
        for text, path in [
            ("打开输出目录", VIDEO_OUTPUT_DIR),
            ("打开日志目录", LOG_DIR),
            ("打开 cookie 目录", COOKIE_DIR),
        ]:
            b = QPushButton(text)
            b.clicked.connect(
                lambda checked, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
            )
            open_row.addWidget(b)
        open_row.addStretch(1)
        form.addRow("", open_row)

        container = QWidget()
        container.setLayout(form)
        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _on_choose_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择默认保存目录", self.dir_edit.text())
        if folder:
            self.dir_edit.setText(folder)
            self.settings.set("save_dir", folder)

    def _on_quality_changed(self, _idx):
        q = self.quality_combo.currentData()
        if q is not None:
            self.settings.set("quality", q.name)

    def _on_theme_changed(self, _idx):
        name = self.theme_combo.currentData()
        if name:
            self.theme_mgr.set_theme(name)

    def _on_check_ffmpeg(self):
        ok = ffmpeg_available()
        self.ffmpeg_status.setText("已安装 ✓" if ok else "未检测到 ffmpeg，请安装并加入系统 PATH")
        self.ffmpeg_status.setStyleSheet(f"color:{'#2e7d32' if ok else '#c62828'};")
