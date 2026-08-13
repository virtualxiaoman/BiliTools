"""日志管线。

三路消息汇入 `app_signals.log_message`：
1. SDK 的 `logging` 记录 → SignalLogHandler（按 level 分类）；
2. SDK 的 `print()`/stderr → StdoutRedirect（普通色，分类器二次着色）；
3. 下载线程结构化事件 → 直接 emit（见 workers/）。

另外：持久化日志文件 + 全局异常钩子（永不闪退）。
"""
import logging
import re
import sys
import traceback
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import qInstallMessageHandler

from src.config.path import OUTPUT_DIR

from frontend.pyside6.signals import AppSignals, LogCategory

LOG_DIR = OUTPUT_DIR / "logs"
LOG_FILE = LOG_DIR / "bilitools.log"

# SDK 内部"视频级批量进度"（如「已下载 3/24 个视频」）→ 深蓝色
_VIDEO_PROGRESS_RE = re.compile(r"已下载\s*\d+/\d+\s*个视频")


def classify(text: str, level: int) -> int:
    """按级别 + 稳定正则对文本分类。"""
    if _VIDEO_PROGRESS_RE.search(text):
        return LogCategory.PROGRESS
    if level >= logging.ERROR:
        return LogCategory.ERROR
    if level == logging.WARNING:
        return LogCategory.WARN
    return LogCategory.NORMAL


class SignalLogHandler(logging.Handler):
    """把 SDK logging 记录转发为日志信号。"""

    def __init__(self, signals: AppSignals):
        super().__init__()
        self.signals = signals
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record):
        try:
            text = self.format(record)
            self.signals.log_message.emit(classify(text, record.levelno), text)
        except Exception:
            pass


class StdoutRedirect:
    """把 sys.stdout / sys.stderr 重定向为日志信号（跨线程安全）。"""

    def __init__(self, signals: AppSignals, is_error: bool = False):
        self.signals = signals
        self.is_error = is_error

    def write(self, text: str) -> int:
        try:
            if not text or text == "\n":
                return len(text)
            # 处理 \r 进度行：只保留最后一段
            if "\r" in text:
                text = text.split("\r")[-1]
            text = text.rstrip("\n")
            if not text:
                return len(text)
            level = logging.ERROR if self.is_error else logging.INFO
            self.signals.log_message.emit(classify(text, level), text)
        except Exception:
            pass
        return len(text)

    def flush(self):
        pass


def install_logging(signals: AppSignals) -> None:
    """挂载 handler、重定向 stdout/stderr、建日志文件。幂等。"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    for h in logger.handlers:
        if getattr(h, "_bilitools_ui", False):
            return  # 已安装

    sh = SignalLogHandler(signals)
    sh._bilitools_ui = True
    logger.addHandler(sh)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(LOG_FILE, maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        fh._bilitools_ui = True
        logger.addHandler(fh)
    except OSError:
        pass

    # 第三方库日志太吵，只保留 warning+
    for noisy in ("urllib3", "requests", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    sys.stdout = StdoutRedirect(signals, is_error=False)
    sys.stderr = StdoutRedirect(signals, is_error=True)


def install_exception_hooks(signals: AppSignals) -> None:
    """全局异常兜底：任何未被捕获的异常都写入界面日志 + 日志文件，程序不闪退。"""

    def excepthook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        logging.getLogger("frontend").error("未捕获异常:\n%s", text)
        signals.log_message.emit(LogCategory.ERROR, f"[未捕获异常] {exc}")

    def unraisable(unraisable_args):
        try:
            err = unraisable_args.exc_value
            logging.getLogger("frontend").error("Unraisable 异常: %r", err)
            signals.log_message.emit(LogCategory.ERROR, f"[未处理异常] {err}")
        except Exception:
            pass

    sys.excepthook = excepthook
    sys.unraisablehook = unraisable

    # 无害的 Qt 提示不刷进界面日志（保留在文件日志里便于排查）
    _IGNORED_QT = ("QFont::setPointSize", "Cannot find font directory")

    def qt_handler(mode, context, message):
        if any(tok in message for tok in _IGNORED_QT):
            logging.getLogger("frontend").debug("[Qt] %s", message)
            return
        cat = LogCategory.ERROR if mode >= 4 else LogCategory.WARN  # 4=QtFatalMsg
        logging.getLogger("frontend").warning("[Qt] %s", message)
        signals.log_message.emit(cat, f"[Qt] {message}")

    qInstallMessageHandler(qt_handler)
