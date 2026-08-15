"""设置页：左侧窄按钮栏分类 + 右侧设置区域（QStackedWidget）。"""
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QScrollArea,
    QSlider, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from src.config.path import COOKIE_ROOT, VIDEO_OUTPUT_DIR, get_cookie_dir, set_cookie_dir
from src.models.download_model import VideoQuality
from src.services.account import AccountManager
from src.util.downloader import ffmpeg_available

from frontend.pyside6 import fonts
from frontend.pyside6.logs import LOG_DIR
from frontend.pyside6.signals import app_signals
from frontend.pyside6.theme import build_qss, get_palette
from frontend.pyside6.workers.login_worker import recheck_login

# 左侧分类（按钮文字 -> 右侧页面索引）
_CATEGORIES = ["下载", "界面", "日志", "目录", "账号"]


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
        self.stack.addWidget(self._build_account_page())    # 4 账号
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

        # 界面缩放（80%~150%，拖动即时生效）
        zoom_row = QHBoxLayout()
        zoom_row.setContentsMargins(0, 0, 0, 0)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(80, 150)
        self.zoom_slider.setValue(int(round(self.settings.get("zoom", 1.0) * 100)))
        self.zoom_slider.setSingleStep(5)
        self.zoom_slider.setTickInterval(10)
        self.zoom_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        self.zoom_label = QLabel(f"{self.zoom_slider.value()}%")
        self.zoom_label.setFixedWidth(46)
        zoom_row.addWidget(self.zoom_slider, 1)
        zoom_row.addWidget(self.zoom_label)
        form.addRow("界面缩放", zoom_row)

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
        ]:
            b = QPushButton(text)
            b.clicked.connect(
                lambda checked, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
            )
            form.addRow("", b)
        b = QPushButton("打开 cookie 目录")
        b.clicked.connect(self._on_open_cookie_dir)
        form.addRow("", b)
        container = QWidget()
        container.setLayout(form)
        return container

    def _build_account_page(self):
        form = QFormLayout()
        form.setVerticalSpacing(16)
        form.setContentsMargins(20, 16, 20, 16)

        # Cookie 保存位置（全局目录，默认 C 盘用户目录）
        self.cookie_dir_edit = QLineEdit(str(get_cookie_dir()))
        btn_cookie_dir = QPushButton("浏览…")
        btn_cookie_dir.clicked.connect(self._on_choose_cookie_dir)
        btn_cookie_reset = QPushButton("恢复默认")
        btn_cookie_reset.clicked.connect(self._on_reset_cookie_dir)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.cookie_dir_edit, 1)
        dir_row.addWidget(btn_cookie_dir)
        dir_row.addWidget(btn_cookie_reset)
        form.addRow("Cookie 保存位置", dir_row)
        self.cookie_dir_edit.editingFinished.connect(self._on_cookie_dir_edited)

        hint = QLabel(
            "默认保存在 C 盘用户目录（%APPDATA%\\xiaoman\\BiliTools\\cookie），"
            "程序文件夹分享/拷贝时不会带出登录凭证。"
        )
        hint.setObjectName("Dim")
        hint.setWordWrap(True)
        form.addRow("", hint)

        btn_open = QPushButton("打开 cookie 目录")
        btn_open.clicked.connect(self._on_open_cookie_dir)
        form.addRow("", btn_open)

        container = QWidget()
        container.setLayout(form)
        return container

    # ---- 账号页事件 ----

    def _on_choose_cookie_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择 Cookie 保存目录", self.cookie_dir_edit.text())
        if folder:
            self._apply_cookie_dir(folder)

    def _on_cookie_dir_edited(self):
        self._apply_cookie_dir(self.cookie_dir_edit.text().strip() or COOKIE_ROOT)

    def _on_reset_cookie_dir(self):
        self._apply_cookie_dir(COOKIE_ROOT)

    def _apply_cookie_dir(self, new_dir):
        new_dir = Path(new_dir).expanduser().resolve()
        old_dir = get_cookie_dir()
        if new_dir == old_dir:
            self.cookie_dir_edit.setText(str(new_dir))
            return
        manager = AccountManager()
        # 先把旧目录下的账号 cookie 迁到新目录并更新映射，再切换全局目录
        manager.relocate(old_dir, new_dir)
        set_cookie_dir(new_dir)
        self.settings.set("cookie_dir", str(new_dir))
        self.cookie_dir_edit.setText(str(new_dir))
        manager.apply_startup()  # 按最新映射重设当前账号 cookie 路径
        recheck_login()

    def _on_open_cookie_dir(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(get_cookie_dir())))

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

    def _on_zoom_changed(self, value):
        """界面缩放：重算默认字体与整份 QSS（所有 px 按比例放大），不重建窗口。"""
        zoom = value / 100.0
        self.settings.set("zoom", zoom)
        self.zoom_label.setText(f"{value}%")
        fonts.set_zoom(zoom)
        app = QApplication.instance()
        if app is not None:
            app.setFont(fonts.app_font())
            app.setStyleSheet(build_qss(get_palette()))
        app_signals.zoom_changed.emit(zoom)

    def _on_check_ffmpeg(self):
        ok = ffmpeg_available()
        self.ffmpeg_status.setText(
            "可用 ✓" if ok
            else "不可用：请安装 ffmpeg 并加入系统 PATH，或执行 pip install imageio-ffmpeg"
        )
        self.ffmpeg_status.setStyleSheet(f"color:{'#2e7d32' if ok else '#c62828'};")
