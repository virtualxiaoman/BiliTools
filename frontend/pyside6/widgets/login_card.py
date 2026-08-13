"""登录状态卡片：头像 / 昵称 / mid。"""
import logging

from PySide6.QtCore import QRectF, Qt, QUrl
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from src.config.path import ASSETS_DIR

from frontend.pyside6.signals import app_signals
from frontend.pyside6.workers.login_worker import query_login_async

logger = logging.getLogger(__name__)

FACE_CACHE_DIR = ASSETS_DIR / "cache"


class LoginCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(92)
        self._pending_face = None

        self._net = QNetworkAccessManager(self)
        self._net.finished.connect(self._on_face_downloaded)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        self.avatar = QLabel()
        self.avatar.setFixedSize(60, 60)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label = QLabel("未登录")
        self.name_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.mid_label = QLabel("请前往「登录」页扫码")
        self.mid_label.setObjectName("Dim")
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setFixedWidth(56)

        info = QVBoxLayout()
        info.setSpacing(2)
        info.addWidget(self.name_label)
        info.addWidget(self.mid_label)
        info.addStretch(1)

        lay.addWidget(self.avatar)
        lay.addLayout(info, 1)
        lay.addWidget(self.btn_refresh)

        self.btn_refresh.clicked.connect(self.refresh)
        app_signals.login_changed.connect(self._render)

    def refresh(self):
        query_login_async(lambda user: app_signals.login_changed.emit(user))

    def _render(self, user):
        if user is None or not getattr(user, "is_login", False):
            self.name_label.setText("未登录")
            self.mid_label.setText("请前往「登录」页扫码")
            self._set_placeholder_avatar()
            return
        self.name_label.setText(user.uname or "已登录")
        self.mid_label.setText(f"mid = {user.mid if user.mid is not None else '?'}")
        self._load_avatar(user.mid, user.face)

    # ---- 头像 ----

    def _load_avatar(self, mid, url):
        if not url:
            self._set_placeholder_avatar()
            return
        cache = FACE_CACHE_DIR / f"face_{mid}.png"
        if cache.exists():
            self._set_avatar(cache)
            return
        FACE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._pending_face = (mid, cache)
        self._net.get(QNetworkRequest(QUrl(url)))

    def _on_face_downloaded(self, reply):
        mid, cache = self._pending_face or (None, None)
        self._pending_face = None
        try:
            data = reply.readAll()
            img = QImage.fromData(data)
            if img.isNull():
                self._set_placeholder_avatar()
                return
            img.save(str(cache))
            self._set_avatar(cache)
        except Exception as e:
            logger.warning("头像下载失败：%s", e)
            self._set_placeholder_avatar()

    def _set_placeholder_avatar(self):
        pm = QPixmap(60, 60)
        pm.fill(QColor("#cfd6de"))
        self.avatar.setPixmap(self._round(pm))

    def _set_avatar(self, path):
        pm = QPixmap(str(path))
        if pm.isNull():
            self._set_placeholder_avatar()
            return
        pm = pm.scaled(60, 60, Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
        self.avatar.setPixmap(self._round(pm))

    def _round(self, pm):
        out = QPixmap(60, 60)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(QRectF(0, 0, 60, 60))
        p.setClipPath(path)
        p.drawPixmap(0, 0, pm)
        p.end()
        return out
