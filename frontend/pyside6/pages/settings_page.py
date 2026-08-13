"""设置页：左侧窄按钮栏分类 + 右侧设置区域（QStackedWidget）。"""
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QScrollArea, QSpinBox,
    QStackedWidget, QVBoxLayout, QWidget,
)

from src.config.path import COOKIE_DIR, VIDEO_OUTPUT_DIR
from src.models.download_model import VideoQuality
from src.util.downloader import ffmpeg_available

from frontend.pyside6.logs import LOG_DIR

# 左侧分类（按钮文字 -> 右侧页面索引）
_CATEGORIES = ["下载", "界面", "日志", "目录"]


class SettingsPage(QWidget):
    def __init__(self, settings, theme_mgr, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.theme_mgr = theme_mgr

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # ---- 左侧：分类按钮栏（窄） ----
        left = QWidget()
        left.setObjectName("Panel")
        left.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        left.setFixedWidth(140)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(6, 10, 6, 10)
        lv.setSpacing(4)
        self._cat_grp = QButtonGroup(self)
        self._cat_grp.setExclusive(True)
        for i, name in enumerate(_CATEGORIES):
            btn = QPushButton(name)
            btn.setObjectName("NavItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._cat_grp.addButton(btn, i)
            lv.addWidget(btn)
        lv.addStretch(1)
        outer.addWidget(left)

        # ---- 右侧：设置区域 ----
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_download_page())   # 0 下载
        self.stack.addWidget(self._build_ui_page())         # 1 界面
        self.stack.addWidget(self._build_log_page())        # 2 日志
        self.stack.addWidget(self._build_dir_page())        # 3 目录
        outer.addWidget(self.stack, 1)

        self._cat_grp.buttonClicked.connect(lambda b: self.stack.setCurrentIndex(self._cat_grp.id(b)))
        first = self._cat_grp.button(0)
        first.setChecked(True)
        self.stack.setCurrentIndex(0)

    # ---- 右侧页面 ----

    def _build_download_page(self):
        form = QFormLayout()
        form.setVerticalSpacing(16)
        form.setContentsMargins(20, 16, 20, 16)

        # 默认保存目录
        self.dir_edit = QLineEdit(self.settings.get("save_dir"))
        btn_dir = QPushButton("浏览…")
        btn_dir.clicked.connect(self._on_choose_dir)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(btn_dir)
        form.addRow("默认保存目录", dir_row)

        # 默认清晰度
        self.quality_combo = QComboBox()
        default_q = getattr(VideoQuality, self.settings.get("quality", "HD4K"), VideoQuality.HD4K)
        for q in VideoQuality:
            self.quality_combo.addItem(q.display_name, q)
        idx = self.quality_combo.findData(default_q)
        self.quality_combo.setCurrentIndex(max(idx, 0))
        self.quality_combo.currentIndexChanged.connect(self._on_quality_changed)
        form.addRow("默认清晰度", self.quality_combo)

        # 默认类型（有且仅有一个）
        self.rb_video = QRadioButton("视频")  # 视频即含声音
        self.rb_audio = QRadioButton("仅音频")
        self.type_grp = QButtonGroup(self)
        self.type_grp.addButton(self.rb_video)
        self.type_grp.addButton(self.rb_audio)
        self.rb_video.setChecked(self.settings.get("media_type") != "audio")
        self.rb_audio.setChecked(self.settings.get("media_type") == "audio")
        self.rb_video.toggled.connect(
            lambda on: self.settings.set("media_type", "video_with_audio") if on else None)
        self.rb_audio.toggled.connect(
            lambda on: self.settings.set("media_type", "audio") if on else None)
        type_row = QHBoxLayout()
        type_row.addWidget(self.rb_video)
        type_row.addWidget(self.rb_audio)
        type_row.addStretch(1)
        form.addRow("默认类型", type_row)

        # ffmpeg 检测
        self.ffmpeg_status = QLabel("")
        btn_ffmpeg = QPushButton("检测 ffmpeg")
        btn_ffmpeg.clicked.connect(self._on_check_ffmpeg)
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.addWidget(btn_ffmpeg)
        ffmpeg_row.addWidget(self.ffmpeg_status, 1)
        form.addRow("音视频合成", ffmpeg_row)

        container = QWidget()
        container.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(container)
        return scroll

    def _build_ui_page(self):
        form = QFormLayout()
        form.setVerticalSpacing(16)
        form.setContentsMargins(20, 16, 20, 16)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.setCurrentIndex(0 if self.settings.get("theme") != "dark" else 1)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        form.addRow("界面主题", self.theme_combo)

        container = QWidget()
        container.setLayout(form)
        return container

    def _build_log_page(self):
        form = QFormLayout()
        form.setVerticalSpacing(16)
        form.setContentsMargins(20, 16, 20, 16)

        self.lines_spin = QSpinBox()
        self.lines_spin.setRange(100, 100000)
        self.lines_spin.setValue(int(self.settings.get("log_max_lines", 1000)))
        self.lines_spin.valueChanged.connect(lambda v: self.settings.set("log_max_lines", v))
        form.addRow("日志最大行数", self.lines_spin)

        self.ts_check = QCheckBox("显示时间戳")
        self.ts_check.setChecked(bool(self.settings.get("log_timestamp", True)))
        self.ts_check.toggled.connect(lambda on: self.settings.set("log_timestamp", on))
        form.addRow("日志", self.ts_check)

        container = QWidget()
        container.setLayout(form)
        return container

    def _build_dir_page(self):
        form = QFormLayout()
        form.setVerticalSpacing(16)
        form.setContentsMargins(20, 16, 20, 16)
        for text, path in [
            ("打开输出目录", VIDEO_OUTPUT_DIR),
            ("打开日志目录", LOG_DIR),
            ("打开 cookie 目录", COOKIE_DIR),
        ]:
            b = QPushButton(text)
            b.clicked.connect(
                lambda checked, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
            )
            form.addRow("", b)
        container = QWidget()
        container.setLayout(form)
        return container

    # ---- 事件 ----

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
