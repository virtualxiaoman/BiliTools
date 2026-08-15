"""全局信号总线：集中承载跨页/跨线程的信号，避免循环依赖。"""
from enum import IntEnum

from PySide6.QtCore import QObject, Signal


class LogCategory(IntEnum):
    """日志类别（颜色映射见 theme.log_colors）。"""

    NORMAL = 0    # 普通信息（黑）
    PROGRESS = 1  # 批量/大进度（深蓝）
    WARN = 2      # 警告（橙）
    ERROR = 3     # 报错（红加粗）
    SUCCESS = 4   # 完成（绿加粗）


class AppSignals(QObject):
    """应用级信号总线（单例）。子线程可安全 emit（自动排队到主线程）。"""

    log_message = Signal(int, str)       # (LogCategory, text)
    login_changed = Signal(object)       # LoginUser | None（未登录/获取失败）
    goto_page = Signal(str)              # 'download' | 'login' | 'settings'
    theme_changed = Signal(str)          # 'light' | 'dark'
    zoom_changed = Signal(float)         # 全局界面缩放系数


# 全局唯一实例
app_signals = AppSignals()
