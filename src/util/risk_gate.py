"""
风控协调器：并发下载时，任一线程触发风控后，所有线程在下一次获取信息前各自暂停。

[设计]
- `mark_risk()`：某线程捕获到风控错误（BiliRiskError / BiliForbiddenError）时调用，
  内部风控事件版本号 +1；
- `pause_before_fetch()`：每次「获取信息」前调用。若自该线程上次检查以来发生过风控，
  则按**本线程独立随机时长**暂停一次（每个线程单独计算，互不影响），随后继续。
- 线程各自用 `threading.local()` 记录已消费的事件版本，保证每个线程对每次风控恰好暂停一次。
"""

import random
import threading
import time


class RiskGate:
    """线程安全的风控事件协调器。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._epoch = 0              # 风控事件版本号
        self._seen = threading.local()  # 各线程已消费的版本号

    def mark_risk(self) -> None:
        """记录一次风控事件（某线程触发风控时调用）。"""
        with self._lock:
            self._epoch += 1

    def pause_before_fetch(self, base: float = 3.0, span: float = 5.0) -> None:
        """在每次获取信息前调用；若发生过风控，按本线程独立随机时长暂停一次。

        :param base: 暂停时长下限（秒）
        :param span: 暂停时长随机跨度（秒），实际为 uniform(base, base + span)
        """
        with self._lock:
            epoch = self._epoch
        if epoch > getattr(self._seen, "epoch", 0):
            wait = random.uniform(base, base + span)
            time.sleep(wait)
            self._seen.epoch = epoch
