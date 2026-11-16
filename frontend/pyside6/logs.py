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
from enum import StrEnum
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import qInstallMessageHandler

from src.config.path import OUTPUT_DIR

from frontend.pyside6.signals import AppSignals, LogCategory

LOG_DIR = OUTPUT_DIR / "logs"
LOG_FILE = LOG_DIR / "bilitools.log"

# SDK 内部"视频级批量进度"（如「已下载 3/24 个视频」）→ 深蓝色
_VIDEO_PROGRESS_RE = re.compile(r"已下载\s*\d+/\d+\s*个视频")

# SDK 直出（BatchProgress display=True）的原始进度行：
# `[1/1] [标题.mp4] [1080P]: 12.3/100.0MB (12.3%)`、`[1/1] [标题]: 准备下载`。
# 这类行按下载块高频刷新，只适合终端；GUI 由任务进度区展示，不能写进日志面板。
_RAW_PROGRESS_RE = re.compile(r"^\[\d+/\d+\]\s*\[")


class LogKind(StrEnum):
    """下载日志的内容分类（用于界面过滤，不影响日志落盘）。"""

    DOWNLOAD_START = "download_start"  # 逐文件开始（正在下载）
    CACHED_SKIP = "cached_skip"        # 缓存命中（已存在，跳过）
    UP_OTHERS = "up_others"            # UP 主空间里的他人联合投稿逐条明细
    COMPLETED = "completed"            # 文件下载完成
    TASK = "task"                      # 任务/汇总/视频级进度
    ACCOUNT = "account"                # 账号、权限、换号
    WARN = "warn"
    ERROR = "error"
    OTHER = "other"


LOG_KIND_LABELS = {
    LogKind.DOWNLOAD_START: "下载开始（正在下载）",
    LogKind.CACHED_SKIP: "缓存跳过（已存在）",
    LogKind.UP_OTHERS: "联合投稿明细",
    LogKind.COMPLETED: "下载完成",
    LogKind.TASK: "任务与汇总",
    LogKind.ACCOUNT: "账号与权限",
    LogKind.WARN: "警告",
    LogKind.ERROR: "错误",
    LogKind.OTHER: "其他",
}

# 默认隐藏逐文件开始、缓存跳过与联合投稿逐条明细：
# 进度看任务进度区，明细看日志文件，界面只留完成/失败等有效信息。
DEFAULT_HIDDEN_KINDS = (LogKind.DOWNLOAD_START, LogKind.CACHED_SKIP, LogKind.UP_OTHERS)

_ACCOUNT_RE = re.compile(r"(改用账号|无播放权限|无大会员|大会员账号|非大会员|联合投稿|充电)")
_TASK_RE = re.compile(
    r"^(已下载\s*\d+/\d+\s*个视频|任务完成|跳过不可见|BV[0-9A-Za-z]+：|"
    r"合集「|收藏夹「|UP主)")



def classify(text: str, level: int) -> int:
    """按级别 + 稳定正则对文本分类。"""
    if _VIDEO_PROGRESS_RE.search(text):
        return LogCategory.PROGRESS
    if level >= logging.ERROR:
        return LogCategory.ERROR
    if level == logging.WARNING:
        return LogCategory.WARN
    return LogCategory.NORMAL


def classify_kind(text: str, category: int = LogCategory.NORMAL) -> LogKind:
    """判断一条日志的内容分类（用于界面过滤，不改变日志落盘）。"""
    raw = str(text or "").lstrip()
    if category == LogCategory.ERROR:
        return LogKind.ERROR
    if category == LogCategory.WARN:
        return LogKind.WARN
    if raw.startswith("正在下载"):
        return LogKind.DOWNLOAD_START
    if raw.startswith("已存在，跳过"):
        return LogKind.CACHED_SKIP
    if raw.startswith("他人稿件："):
        return LogKind.UP_OTHERS
    if raw.startswith("下载完成"):
        return LogKind.COMPLETED
    if _ACCOUNT_RE.search(raw):
        return LogKind.ACCOUNT
    if _TASK_RE.match(raw):
        return LogKind.TASK
    return LogKind.OTHER


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
            if _RAW_PROGRESS_RE.match(text.strip()):
                # 原始字节进度不进界面；任务进度区已经展示同一条信息。
                return len(text)
            level = logging.ERROR if self.is_error else logging.INFO
            self.signals.log_message.emit(classify(text, level), text)
        except Exception:
            pass
        return len(text)

    def flush(self):
        pass


def install_logging(signals: AppSignals) -> None:
    """挂载 handler、重定向 stdout/stderr、建日志文件。幂等。

    界面日志保持简洁：仅 INFO 及以上进入 UI；DEBUG（含 ffmpeg 合成命令、逐P信息等
    细节）只写入文件日志供排查。
    """
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    for h in logger.handlers:
        if getattr(h, "_bilitools_ui", False):
            return  # 已安装

    sh = SignalLogHandler(signals)
    sh.setLevel(logging.INFO)  # 界面只显示 INFO+
    sh._bilitools_ui = True
    logger.addHandler(sh)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(LOG_FILE, maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setLevel(logging.DEBUG)  # 文件保留 DEBUG，供排查
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
        signals.log_message.emit(LogCategory.ERROR, f"[未捕获异常] {exc or type(exc).__name__}")

    def unraisable(unraisable_args):
        try:
            err = unraisable_args.exc_value
            logging.getLogger("frontend").error("Unraisable 异常: %r", err)
            signals.log_message.emit(
                LogCategory.ERROR, f"[未处理异常] {err or type(err).__name__}"
            )
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
