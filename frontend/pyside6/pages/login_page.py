"""登录页：扫码登录 + 退出登录。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from src.config.path import get_qr_image_path
from src.services.account import AccountManager

from frontend.pyside6.signals import LogCategory, app_signals
from frontend.pyside6.workers.login_worker import QrLoginWorker, _drop, _keepalive, recheck_login


class LoginPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._started = False   # 是否已自动生成过二维码（登录页只自动生成一次）
        self._logged_in = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)

        card = QWidget()
        card.setObjectName("Card")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setFixedWidth(480)
        v = QVBoxLayout(card)
        v.setContentsMargins(30, 26, 30, 26)
        v.setSpacing(14)

        title = QLabel("扫码登录 B 站账号")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("PageTitle")  # 字体由 theme QSS 控制（粗体、随缩放）

        self.qr_label = QLabel("正在生成二维码…")
        self.qr_label.setFixedSize(240, 240)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setStyleSheet(
            "border: 1px solid #c8c8c8; border-radius: 8px; background: #ffffff; color: #888888;"
        )

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("Dim")

        self.btn_generate = QPushButton("登录新账号")

        self.info_label = QLabel("未登录")
        self.btn_logout = QPushButton("退出登录")
        info_row = QHBoxLayout()
        info_row.addStretch(1)
        info_row.addWidget(self.info_label)
        info_row.addSpacing(12)
        info_row.addWidget(self.btn_logout)
        info_row.addStretch(1)

        v.addWidget(title)
        v.addWidget(self.qr_label, alignment=Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.status_label)
        v.addWidget(self.btn_generate)
        v.addLayout(info_row)

        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

        self.btn_generate.clicked.connect(self.start)
        self.btn_logout.clicked.connect(self._on_logout)
        app_signals.login_changed.connect(self._update_info)

    def showEvent(self, event):
        super().showEvent(event)
        # 已登录则不再自动生成二维码（用户手动点"重新生成"才会刷新）
        if not self._started and not self._logged_in:
            self._started = True
            self.start()

    # ---- 扫码流程 ----

    def start(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
        self.status_label.setText("正在生成二维码…")
        self.qr_label.setText("生成中…")
        w = QrLoginWorker()
        w.qr_ready.connect(self._show_qr)
        w.status.connect(self._on_status)
        w.done.connect(self._on_done)
        w.finished.connect(lambda: _drop(w))
        _keepalive.append(w)
        self._worker = w
        w.start()

    def _show_qr(self):
        qr_path = get_qr_image_path()
        if qr_path.exists():
            pm = QPixmap(str(qr_path))
            if not pm.isNull():
                self.qr_label.setPixmap(pm.scaled(
                    240, 240, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
                self.qr_label.setFixedSize(240, 240)
                return
        self.qr_label.setText("二维码生成失败，请点击「重新生成」")

    def _on_status(self, code, text):
        self.status_label.setText(text)

    def _on_done(self, ok, msg):
        self.status_label.setText(msg)
        if ok:
            app_signals.log_message.emit(LogCategory.SUCCESS, msg)
        else:
            app_signals.log_message.emit(LogCategory.WARN, f"登录未完成：{msg}")

    # ---- 登录信息 ----

    def _update_info(self, user):
        logged = user is not None and getattr(user, "is_login", False)
        self._logged_in = logged
        if logged:
            self.info_label.setText(f"已登录：{user.uname}（mid={user.mid}）")
            self.btn_logout.setEnabled(True)
            # 已登录：停止可能仍在轮询的二维码线程，不再展示/生成二维码
            if self._worker and self._worker.isRunning():
                self._worker.stop()
            self.qr_label.clear()
            self.qr_label.setText("已登录，无需重复扫码")
            self.status_label.setText("")
        else:
            self.info_label.setText("未登录")
            self.btn_logout.setEnabled(False)
            self.status_label.setText("")

    def _on_logout(self):
        AccountManager().remove_current()  # 删 cookie 文件 + 删映射条目 + 清缓存 + 切下一个账号
        app_signals.log_message.emit(LogCategory.NORMAL, "已退出登录")
        recheck_login()  # 若有其他账号，刷新到新当前账号；否则未登录
