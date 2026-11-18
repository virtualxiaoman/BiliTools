"""左侧下载输入面板：多个来源页签 + 共用选项 + 下载按钮 + 任务进度区。"""
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QIntValidator
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QRadioButton, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
)

from src.config.path import COLLECTION_OUTPUT_DIR
from src.models.download_model import VideoQuality

from frontend.pyside6.signals import LogCategory, app_signals
from frontend.pyside6.utils import (
    NeedsUrlResolution, extract_page_from_url, normalize_bvid, normalize_fav,
    normalize_mid, normalize_season,
)
from frontend.pyside6.widgets.dressup_panel import DressupPanel
from frontend.pyside6.widgets.task_progress_panel import TaskProgressPanel

_HINTS = [
    "支持 BV号 / av号 / 视频链接",
    "支持 fid / 收藏夹链接",
    "支持 BV号(自动获取对应的合集) / sid / 合集链接",
    "支持 mid / 空间链接",
    "关键词同时搜索表情包、收藏集与主题装扮；勾选后可批量下载",
]


class NumberEdit(QLineEdit):
    """无上下箭头的数字输入框（QLineEdit + 整型校验），键盘可用上下方向键调整数字。

    QSpinBox 的上下箭头与占位提示不可兼得，故用 QLineEdit 实现：
    - 无箭头按钮；
    - 鼠标/键盘直接输入数字（QIntValidator 限 minimum~maximum）；
    - 键盘 ↑/↓ 上下调整（与 QSpinBox 行为一致）。

    :param minimum: 允许的最小值
    :param maximum: 允许的最大值
    :param placeholder: 占位提示文本
    """

    def __init__(self, minimum: int = 1, maximum: int = 999, placeholder: str = "P几", parent=None):
        super().__init__(parent)
        self.minimum = minimum
        self.maximum = maximum
        self.setPlaceholderText(placeholder)
        self.setValidator(QIntValidator(minimum, maximum, self))
        self.setMaximumWidth(56)
        self.setText(str(minimum))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def value(self) -> int:
        try:
            return max(self.minimum, min(self.maximum, int(self.text() or str(self.minimum))))
        except ValueError:
            return self.minimum

    def setValue(self, v: int) -> None:
        self.setText(str(max(self.minimum, min(self.maximum, int(v)))))

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
        self.dir_label = QLabel("保存到")
        self.dir_edit = QLineEdit(settings.get("save_dir"))
        self.dir_edit.setFixedHeight(38)
        self._normal_save_dir = self.dir_edit.text()
        self._collection_asset_active = False
        self._save_dir_timer = QTimer(self)
        self._save_dir_timer.setSingleShot(True)
        self._save_dir_timer.setInterval(350)
        self._save_dir_timer.timeout.connect(self._persist_save_dir)
        self.dir_edit.textChanged.connect(self._on_save_dir_changed)
        self.dir_edit.editingFinished.connect(self._on_save_dir_finished)
        app_signals.save_dir_changed.connect(self._apply_save_dir)
        self.btn_browse = QPushButton("浏览…")
        dir_row.addWidget(self.dir_label)
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(self.btn_browse)
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
        self._inputs = [
            self.input_bv, self.input_fav, self.input_season, self.input_up,
        ]
        # QTabWidget 会把直接作为页签内容的 QLineEdit 拉伸到整个内容区。
        # 不仅固定输入框高度，还用一个带顶部对齐的容器承载它，避免不同
        # Qt 样式或全局缩放策略再次把单行输入框拉伸成多行区域。
        for input_edit, name in zip(self._inputs, ["视频", "收藏夹", "合集", "UP主"]):
            self.tabs.addTab(self._make_input_tab(input_edit), name)
        self.dressup_panel = DressupPanel()
        self.tabs.addTab(self.dressup_panel, "装扮")
        outer.addWidget(self.tabs)
        self.hint = QLabel(_HINTS[0])
        self.hint.setObjectName("Hint")
        outer.addWidget(self.hint)


        # ---- 范围（仅视频页签显示） ----
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
        self.spin_page = NumberEdit()
        rr.addWidget(QLabel("范围："))
        rr.addWidget(self.rb_all)
        rr.addWidget(self.rb_single)
        rr.addWidget(self.spin_page)
        rr.addStretch(1)
        outer.addWidget(self.range_row)

        # ---- 类型 ----
        self.type_row = QWidget()
        type_row = QHBoxLayout(self.type_row)
        type_row.setContentsMargins(0, 0, 0, 0)
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
        outer.addWidget(self.type_row)

        # ---- 清晰度 ----
        self.quality_row = QWidget()
        q_row = QHBoxLayout(self.quality_row)
        q_row.setContentsMargins(0, 0, 0, 0)
        self.quality_combo = QComboBox()
        default_quality = getattr(VideoQuality, self.settings.get("quality", "HD4K"), VideoQuality.HD4K)
        for q in VideoQuality:
            self.quality_combo.addItem(q.display_name, q)
        idx = self.quality_combo.findData(default_quality)
        self.quality_combo.setCurrentIndex(idx if idx >= 0 else 0)
        q_row.addWidget(QLabel("优先清晰度："))
        q_row.addWidget(self.quality_combo, 1)
        outer.addWidget(self.quality_row)

        # ---- 下载选项 ----
        self.force_check = QCheckBox("忽略缓存")
        self.force_check.setToolTip("忽略所有缓存；目标文件名完全一致时覆盖，否则保留旧文件并下载新文件")
        self.dynamic_check = QCheckBox("包含动态视频")
        self.dynamic_check.setToolTip(
            "UP 主页签：从动态流补充只发布在动态里的视频（不在投稿列表）。\n"
            "首次会多花些时间扫描，之后使用增量快照缓存。"
        )
        self.dynamic_check.setChecked(True)
        self.dynamic_check.setVisible(False)
        options_row = QHBoxLayout()
        options_row.setContentsMargins(0, 0, 0, 0)
        options_row.addWidget(self.force_check)
        options_row.addWidget(self.dynamic_check)
        options_row.addStretch(1)
        outer.addLayout(options_row)

        # ---- 下载按钮 ----
        self.btn_download = QPushButton("下载")
        self.btn_download.setObjectName("Primary")
        self.btn_download.setFixedHeight(38)
        outer.addWidget(self.btn_download)

        # ---- 任务进度区 ----
        self.label_tasks = QLabel("任务进度")
        self.label_tasks.setObjectName("SectionTitle")  # 字体由 theme QSS 控制（粗体、随缩放）
        outer.addWidget(self.label_tasks)
        self.task_panel = TaskProgressPanel()
        outer.addWidget(self.task_panel, 1)

        # ---- 打开输出文件夹（左列最下方） ----
        self.btn_open_dir = QPushButton("打开输出文件夹")
        outer.addWidget(self.btn_open_dir)

        self.btn_browse.clicked.connect(self._on_browse)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.btn_download.clicked.connect(self._on_download)
        self.btn_open_dir.clicked.connect(self._on_open_output_dir)
        self.input_bv.textChanged.connect(self._on_bv_input_changed)
        # 普通来源只需要一行输入；装扮页则需要把搜索结果列表展开。
        self._update_tabs_layout(self.tabs.currentIndex())

    # ---- 供 DownloadPage 连接 manager 信号 ----

    def on_task_started(self, tid, desc):
        self.task_panel.add_task(tid, desc, on_cancel=self._on_cancel_task)

    def _on_cancel_task(self, tid):
        """终止任务前确认：删除未完成临时文件，已完成文件保留。"""
        answer = QMessageBox.question(
            self, "终止下载",
            "确定终止该任务吗？\n\n"
            "正在下载的临时文件会被删除；已经下载完成的文件会保留。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self.manager.cancel(tid):
            self.task_panel.set_cancelling(tid)

    def on_task_progress(self, tid, done, total):
        self.task_panel.update_progress(tid, done, total)

    def on_task_phase(self, tid, text):
        self.task_panel.set_phase(tid, text)

    def on_task_finished(self, tid, success, summary):
        self.task_panel.finish_task(tid, success, summary)

    # ---- 内部 ----

    @staticmethod
    def _make_input_tab(input_edit: QLineEdit) -> QWidget:
        """将单行输入框放在页签顶部，避免 QTabWidget 拉伸输入框本身。"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        input_edit.setFixedHeight(34)
        layout.addWidget(input_edit, 0, Qt.AlignmentFlag.AlignTop)
        layout.addStretch(1)
        return page

    def _update_tabs_layout(self, idx: int) -> None:
        """按当前页签内容调整高度，避免普通输入页留下大片空白区域。

        视频、收藏夹、合集和 UP 主页签只有一个单行输入框；如果让
        ``QTabWidget`` 使用默认的 Expanding 策略，页签内容区会填满左侧面板，
        输入框下方就会出现一整块无意义的背景。装扮页需要展示可滚动结果列表，
        因此仅该页签保留可扩展高度。
        """
        if idx == 4:
            self.tabs.setMinimumHeight(0)
            self.tabs.setMaximumHeight(16777215)
            self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        else:
            # 24px 左右的页签栏 + 34px 输入框 + 少量边距。
            self.tabs.setFixedHeight(64)
            self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tabs.updateGeometry()

    def _on_tab_changed(self, idx):
        self._update_tabs_layout(idx)
        is_dressup = idx == 4
        self.range_row.setVisible(idx == 0)  # 范围选项仅视频页签可用
        self.dynamic_check.setVisible(idx == 3)  # 仅 UP 主页签可补充动态视频
        self.type_row.setVisible(not is_dressup)
        self.quality_row.setVisible(not is_dressup)
        self.btn_download.setText("下载选中" if is_dressup else "下载")
        if is_dressup:
            # 在固定目录页签间切换时，不要把 ``output/收藏集`` 误记为普通保存目录。
            if not self._collection_asset_active:
                self._normal_save_dir = self.dir_edit.text()
            self._collection_asset_active = True
            self.dir_label.setText("保存到（固定）")
            self.dir_edit.setText(str(COLLECTION_OUTPUT_DIR))
            self.dir_edit.setEnabled(False)
            self.btn_browse.setEnabled(False)
        else:
            self._collection_asset_active = False
            self.dir_label.setText("保存到")
            self.dir_edit.setEnabled(True)
            self.btn_browse.setEnabled(True)
            self.dir_edit.setText(self._normal_save_dir or self.settings.get("save_dir"))
        self.hint.setText(_HINTS[idx])

    # ---- 保存目录持久化 ----

    def _on_save_dir_changed(self, _text):
        if not self._collection_asset_active:
            self._save_dir_timer.start()

    def _on_save_dir_finished(self):
        self._save_dir_timer.stop()
        self._persist_save_dir(normalize=True)

    def _persist_save_dir(self, normalize=False):
        """把“保存到”写入设置，下次启动继续使用；装扮页固定目录不参与。"""
        if self._collection_asset_active:
            return
        text = self.dir_edit.text().strip()
        if not text:
            return
        if normalize:
            try:
                normalized = str(Path(text).expanduser().resolve())
            except OSError:
                normalized = text
            if normalized != self.dir_edit.text():
                self.dir_edit.setText(normalized)
            text = normalized
        self._normal_save_dir = text
        if self.settings.get("save_dir") != text:
            self.settings.set("save_dir", text)
            app_signals.save_dir_changed.emit(text)

    def _apply_save_dir(self, text):
        """设置页修改保存目录后同步到下载页；装扮页固定目录时不覆盖输入框。"""
        if not text:
            return
        self._save_dir_timer.stop()
        self._normal_save_dir = text
        if not self._collection_asset_active and self.dir_edit.text() != text:
            self.dir_edit.setText(text)

    def _on_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录", self.dir_edit.text())
        if folder:
            self.dir_edit.setText(folder)
            self._persist_save_dir()

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

    def _parallel_options(self):
        """读取设置页维护的全局并发线程数与多账号分流开关。"""
        threads = max(1, min(5, int(self.settings.get("download_threads", 2))))
        distribute = bool(self.settings.get("distribute_accounts", True))
        return threads, distribute

    def _build_spec(self):
        tab = self.tabs.currentIndex()
        threads, distribute = self._parallel_options()
        if tab == 4:
            items = self.dressup_panel.selected_items()
            if not items:
                app_signals.log_message.emit(LogCategory.WARN, "请先勾选要下载的装扮/表情包")
                return None
            names = "、".join(str(item.get("name") or "") for item in items[:3])
            suffix = f" 等 {len(items)} 项" if len(items) > 3 else ""
            return {
                "source": "dressup",
                "input": items,
                "scope": "all",
                "page": 1,
                "media_type": "dressup",
                "quality": self.quality_combo.currentData() or VideoQuality.HD4K,
                "save_dir": str(COLLECTION_OUTPUT_DIR),
                "threads": threads,
                "distribute_accounts": distribute,
                "desc": f"装扮 {names}{suffix}",
            }
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
                        "save_dir": save_dir, "threads": threads,
                        "distribute_accounts": distribute,
                         "cache_dirs": self.settings.get("cache_dirs", []),
                         "force": self.force_check.isChecked(), "desc": desc}
            if tab == 1:
                fid = normalize_fav(raw)
                return {"source": "fav", "input": fid, "scope": "all", "page": 1,
                        "media_type": media_type, "quality": quality,
                        "save_dir": save_dir, "threads": threads,
                        "distribute_accounts": distribute,
                         "cache_dirs": self.settings.get("cache_dirs", []),
                         "force": self.force_check.isChecked(), "desc": f"收藏夹 {fid}"}
            if tab == 2:
                kind, val, mid = normalize_season(raw)
                return {"source": "season", "input": (kind, val, mid), "scope": "all", "page": 1,
                        "media_type": media_type, "quality": quality,
                        "save_dir": save_dir, "threads": threads,
                        "distribute_accounts": distribute,
                         "cache_dirs": self.settings.get("cache_dirs", []),
                         "force": self.force_check.isChecked(), "desc": f"合集 {val}"}
            if tab == 3:
                mid = normalize_mid(raw)
                return {"source": "up", "input": mid, "scope": "all", "page": 1,
                        "media_type": media_type, "quality": quality,
                        "save_dir": save_dir, "threads": threads,
                        "distribute_accounts": distribute,
                         "cache_dirs": self.settings.get("cache_dirs", []),
                         "force": self.force_check.isChecked(),
                         "include_dynamic": self.dynamic_check.isChecked(),
                         "desc": f"UP主 {mid}"}
        except NeedsUrlResolution:
            # 短链等本地解析不了的链接：先建 pending 任务，交给下载线程跟随跳转，
            # 避免在界面线程发 HTTP 请求卡住 UI
            return self._build_pending_spec(tab, raw, media_type, quality, save_dir)
        except ValueError as e:
            app_signals.log_message.emit(LogCategory.ERROR, f"输入无效：{e}")
            return None
        return None

    def _build_pending_spec(self, tab, raw, media_type, quality, save_dir):
        """本地解析不出的链接（如 b23.tv 短链）→ 原样入 spec，由 worker 线程解析。"""
        sources = ["bv", "fav", "season", "up"]
        labels = ["视频", "收藏夹", "合集", "UP主"]
        scope = "single" if self.rb_single.isChecked() else "all"
        page = self.spin_page.value()
        threads, distribute = self._parallel_options()
        return {
            "source": sources[tab],
            "input": raw,
            "pending_resolve": True,
            "scope": scope if tab == 0 else "all",
            "page": page if tab == 0 else 1,
            "media_type": media_type,
            "quality": quality,
            "save_dir": save_dir,
            "threads": threads,
            "distribute_accounts": distribute,
            "cache_dirs": self.settings.get("cache_dirs", []),
            "force": self.force_check.isChecked(),
            "include_dynamic": self.dynamic_check.isChecked(),
            "desc": f"{labels[tab]}（解析链接中…）",
        }

    def _on_download(self):
        spec = self._build_spec()
        if spec is None:
            return
        if not self._confirm_account_quality(spec):
            return
        self.manager.submit(spec)

    @staticmethod
    def _needs_account_quality_prompt(spec) -> bool:
        """只有会走多账号分流、且目标清晰度高于 1080P 时才需要提示大会员差异。"""
        if spec.get("source") not in ("bv", "fav", "season", "up"):
            return False
        if spec.get("source") == "bv" and spec.get("scope") == "single":
            return False
        if not spec.get("distribute_accounts") or int(spec.get("threads", 1)) <= 1:
            return False
        return int(spec.get("quality") or 0) > int(VideoQuality.P1080)

    def _confirm_account_quality(self, spec) -> bool:
        """检测各账号大会员状态并确认本次下载的清晰度策略；返回 False 表示取消下载。"""
        if not self._needs_account_quality_prompt(spec):
            return True
        from PySide6.QtWidgets import QProgressDialog

        # 探测会请求 nav：放到子线程，界面线程只负责转圈，避免卡住主窗口。
        dialog = QProgressDialog("正在检查账号大会员状态…", None, 0, 0, self)
        dialog.setWindowTitle("多账号清晰度")
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setCancelButton(None)
        dialog.setMinimumDuration(0)
        dialog.show()
        try:
            caps = self._probe_capabilities()
        except Exception:
            app_signals.log_message.emit(LogCategory.WARN, "账号大会员状态检测失败，本次不限制多账号清晰度")
            return True
        finally:
            dialog.close()
        if len(caps) < 2:
            return True
        non_vip = [cap for cap in caps if cap.is_vip is False]
        vip_names = [cap.uname for cap in caps if cap.is_vip]
        if not non_vip or not vip_names:
            return True
        names = "".join(f"「{cap.uname}」" for cap in non_vip)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("多账号清晰度提示")
        box.setText(
            f"当前开启了多账号分流，但账号{names}没有大会员，请选择是否忽略这些账号？\n"
            f"忽略：只采用有大会员的账号下载；\n"
            f"不忽略：非大会员账号最高只下载 1080P 视频。"
        )
        ignore_btn = box.addButton("忽略这些账号", QMessageBox.ButtonRole.AcceptRole)
        keep_btn = box.addButton("不忽略（最高 1080P）", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(keep_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is cancel_btn:
            return False
        if clicked is ignore_btn:
            spec["account_quality_policy"] = "vip_only"
            app_signals.log_message.emit(
                LogCategory.NORMAL, "本次下载仅使用大会员账号：" + "、".join(vip_names))
        elif clicked is keep_btn:
            spec["account_quality_policy"] = "cap_1080p"
            app_signals.log_message.emit(LogCategory.NORMAL, "本次下载非大会员账号最高 1080P")
        return True

    @staticmethod
    def _probe_capabilities():
        """在子线程探测账号能力，界面线程循环刷新进度对话框。"""
        import threading

        from src.services.account_capability import list_account_capabilities

        outcome = {}

        def run():
            try:
                outcome["caps"] = list_account_capabilities()
            except Exception as exc:
                outcome["error"] = exc

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        while thread.is_alive():
            QApplication.processEvents()
            thread.join(0.05)
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("caps") or []
