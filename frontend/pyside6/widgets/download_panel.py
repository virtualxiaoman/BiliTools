"""左侧下载输入面板：四个来源页签 + 共用选项 + 下载按钮 + 任务进度区。"""
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QIntValidator
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QTabWidget, QVBoxLayout, QWidget,
)

from src.models.download_model import VideoQuality

from frontend.pyside6.signals import LogCategory, app_signals
from frontend.pyside6.utils import (
    extract_page_from_url, normalize_bvid, normalize_fav, normalize_mid,
    normalize_season,
)
from frontend.pyside6.widgets.task_progress_panel import TaskProgressPanel

_HINTS = [
    "支持 BV号 / av号 / 视频链接",
    "支持 fid / 收藏夹链接",
    "支持 BV号(自动获取对应的合集) / sid / 合集链接",
    "支持 mid / 空间链接",
]


class PNumberEdit(QLineEdit):
    """P 序号输入框：无上下箭头（QLineEdit），键盘可用上下方向键改数字，占位提示"P几"。

    QSpinBox 的上下箭头与占位提示不可兼得，故用 QLineEdit + 整型校验实现：
    - 无箭头按钮；
    - 鼠标/键盘直接输入数字（QIntValidator 限 1~999）；
    - 键盘 ↑/↓ 上下调整（与 QSpinBox 行为一致）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("P几")
        self.setValidator(QIntValidator(1, 999, self))
        self.setMaximumWidth(56)
        self.setText("1")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def value(self) -> int:
        try:
            return max(1, min(999, int(self.text() or "1")))
        except ValueError:
            return 1

    def setValue(self, v: int) -> None:
        self.setText(str(max(1, min(999, int(v)))))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            delta = 1 if event.key() == Qt.Key.Key_Up else -1
            self.setValue(self.value() + delta)
            return
        super().keyPressEvent(event)


class DownloadPanel(QWidget):
    def __init__(self, manager, settings, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.settings = settings
        self.setObjectName("Panel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(400)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        # ---- 保存目录 ----
        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit(settings.get("save_dir"))
        btn_browse = QPushButton("浏览…")
        dir_row.addWidget(QLabel("保存到"))
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(btn_browse)
        outer.addLayout(dir_row)

        # ---- 来源页签 ----
        self.tabs = QTabWidget()
        self.input_bv = QLineEdit()
        self.input_bv.setPlaceholderText("例如 BV1ov42117yC")
        self.input_fav = QLineEdit()
        self.input_fav.setPlaceholderText("例如 3953119978")
        self.input_season = QLineEdit()
        self.input_season.setPlaceholderText("例如 BV1Q43w6QETb 或 sid=8683221")
        self.input_up = QLineEdit()
        self.input_up.setPlaceholderText("例如 249056021")
        self._inputs = [self.input_bv, self.input_fav, self.input_season, self.input_up]
        for w, name in zip(self._inputs, ["视频BV", "收藏夹", "合集", "UP主"]):
            self.tabs.addTab(w, name)
        outer.addWidget(self.tabs)
        self.hint = QLabel(_HINTS[0])
        self.hint.setObjectName("Hint")
        outer.addWidget(self.hint)

        # ---- 范围（仅视频BV页签显示） ----
        self.range_row = QWidget()
        rr = QHBoxLayout(self.range_row)
        rr.setContentsMargins(0, 0, 0, 0)
        self.rb_all = QRadioButton("全部P")
        self.rb_single = QRadioButton("单P")
        self.rb_all.setChecked(True)
        # 显式分组，保证「有且仅有一个」被选中
        self.range_grp = QButtonGroup(self)
        self.range_grp.addButton(self.rb_all)
        self.range_grp.addButton(self.rb_single)
        self.spin_page = PNumberEdit()
        rr.addWidget(QLabel("范围："))
        rr.addWidget(self.rb_all)
        rr.addWidget(self.rb_single)
        rr.addWidget(self.spin_page)
        rr.addStretch(1)
        outer.addWidget(self.range_row)

        # ---- 类型 ----
        type_row = QHBoxLayout()
        self.rb_video = QRadioButton("视频")  # 视频即含声音，无需括号说明
        self.rb_audio = QRadioButton("仅音频")
        # 显式分组，保证「有且仅有一个」被选中
        self.type_grp = QButtonGroup(self)
        self.type_grp.addButton(self.rb_video)
        self.type_grp.addButton(self.rb_audio)
        self.rb_video.setChecked(self.settings.get("media_type") != "audio")
        self.rb_audio.setChecked(self.settings.get("media_type") == "audio")
        type_row.addWidget(QLabel("类型："))
        type_row.addWidget(self.rb_video)
        type_row.addWidget(self.rb_audio)
        type_row.addStretch(1)
        outer.addLayout(type_row)

        # ---- 清晰度 ----
        q_row = QHBoxLayout()
        self.quality_combo = QComboBox()
        default_quality = getattr(VideoQuality, self.settings.get("quality", "HD4K"), VideoQuality.HD4K)
        for q in VideoQuality:
            self.quality_combo.addItem(q.display_name, q)
        idx = self.quality_combo.findData(default_quality)
        self.quality_combo.setCurrentIndex(idx if idx >= 0 else 0)
        q_row.addWidget(QLabel("优先清晰度："))
        q_row.addWidget(self.quality_combo, 1)
        outer.addLayout(q_row)

        # ---- 下载按钮 ----
        self.btn_download = QPushButton("下载")
        self.btn_download.setObjectName("Primary")
        self.btn_download.setFixedHeight(38)
        outer.addWidget(self.btn_download)

        # ---- 任务进度区 ----
        outer.addWidget(QLabel("任务进度"))
        self.task_panel = TaskProgressPanel()
        outer.addWidget(self.task_panel, 1)

        # ---- 打开输出文件夹（左列最下方） ----
        self.btn_open_dir = QPushButton("打开输出文件夹")
        outer.addWidget(self.btn_open_dir)

        btn_browse.clicked.connect(self._on_browse)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.btn_download.clicked.connect(self._on_download)
        self.btn_open_dir.clicked.connect(self._on_open_output_dir)
        self.input_bv.textChanged.connect(self._on_bv_input_changed)

    # ---- 供 DownloadPage 连接 manager 信号 ----

    def on_task_started(self, tid, desc):
        self.task_panel.add_task(tid, desc)

    def on_task_progress(self, tid, done, total):
        self.task_panel.update_progress(tid, done, total)

    def on_task_phase(self, tid, text):
        self.task_panel.set_phase(tid, text)

    def on_task_finished(self, tid, success, summary):
        self.task_panel.finish_task(tid, success, summary)

    # ---- 内部 ----

    def _on_tab_changed(self, idx):
        self.range_row.setVisible(idx == 0)  # 范围选项仅视频BV页签可用
        self.hint.setText(_HINTS[idx])

    def _on_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", self.dir_edit.text())
        if folder:
            self.dir_edit.setText(folder)

    def _on_open_output_dir(self):
        folder = Path(self.dir_edit.text().strip() or self.settings.get("save_dir"))
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _on_bv_input_changed(self, text):
        """输入的视频链接带 p=n → 界面自动切到「单P」并填入该序号。"""
        if not text.strip() or "http" not in text.lower():
            return
        page = extract_page_from_url(text)
        if page is not None:
            self.rb_single.setChecked(True)
            self.spin_page.setValue(page)

    def _current_input(self):
        return self._inputs[self.tabs.currentIndex()]

    def _build_spec(self):
        tab = self.tabs.currentIndex()
        raw = self._current_input().text().strip()
        if not raw:
            app_signals.log_message.emit(LogCategory.WARN, "请输入下载内容")
            return None
        save_dir = self.dir_edit.text().strip() or self.settings.get("save_dir")
        media_type = "video_with_audio" if self.rb_video.isChecked() else "audio"
        quality = self.quality_combo.currentData() or VideoQuality.HD4K
        try:
            if tab == 0:
                bvid = normalize_bvid(raw)
                # 尊重用户当前的「范围」选择：输入链接时的 p=n 自动切换只发生在
                # textChanged（_on_bv_input_changed），用户若手动改回「全部P」则以下全部P下载
                scope = "single" if self.rb_single.isChecked() else "all"
                page = self.spin_page.value()
                desc = f"视频 {bvid}" + (f"（P{page}）" if scope == "single" else "（全部分P）")
                return {"source": "bv", "input": bvid, "scope": scope, "page": page,
                        "media_type": media_type, "quality": quality,
                        "save_dir": save_dir, "desc": desc}
            if tab == 1:
                fid = normalize_fav(raw)
                return {"source": "fav", "input": fid, "scope": "all", "page": 1,
                        "media_type": media_type, "quality": quality,
                        "save_dir": save_dir, "desc": f"收藏夹 {fid}"}
            if tab == 2:
                kind, val, mid = normalize_season(raw)
                return {"source": "season", "input": (kind, val, mid), "scope": "all", "page": 1,
                        "media_type": media_type, "quality": quality,
                        "save_dir": save_dir, "desc": f"合集 {val}"}
            if tab == 3:
                mid = normalize_mid(raw)
                return {"source": "up", "input": mid, "scope": "all", "page": 1,
                        "media_type": media_type, "quality": quality,
                        "save_dir": save_dir, "desc": f"UP主 {mid}"}
        except ValueError as e:
            app_signals.log_message.emit(LogCategory.ERROR, f"输入无效：{e}")
            return None
        return None

    def _on_download(self):
        spec = self._build_spec()
        if spec is not None:
            self.manager.submit(spec)
