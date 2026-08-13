"""BatchProgress 兼容对象 → Qt 信号。

SDK 的下载方法接受一个鸭子类型的 progress 对象（n/label/display +
start/set_quality/add/update/status/finish/make_stream_callback/iter_count）。
本对象不 print，而是把事件转发为 Qt 信号：

- 字节进度 → worker.progress（实时百分比，任务进度区覆盖式刷新）；
- 阶段文本（如 ffmpeg 合成中）→ worker.phase；
- 里程碑（第 i/n 个、单文件完成）→ worker.milestone（追加进日志）。
"""
from frontend.pyside6.signals import LogCategory


class ProgressAdapter:
    def __init__(self, n, label, worker):
        self.n = n
        self.label = label
        self.worker = worker
        self.display = False
        self.current_index = 0
        self.current_name = ""
        self.current_done = 0
        self._stream_totals = []
        self._mono = 0          # 单调文件序号：fav/up 循环调用 download_all_pages 时 i 会逐视频重置，用自增代替
        self._last_emitted = 0
        self._throttle = 512 * 1024  # 进度信号至少间隔 512KB，避免高频刷新

    def start(self, index, name):
        self._mono += 1
        self.current_index = index
        self.current_name = name
        self.current_done = 0
        self.current_quality = None
        self._stream_totals = []
        self._last_emitted = 0
        # 延迟输出"正在下载"行：等 set_quality（拿到真实清晰度）或首个字节或完成时再输出
        self._pending_line = True

    def set_quality(self, quality):
        self.current_quality = quality
        self._flush_pending_line()

    def add(self, delta, total, stream_id=0):
        self.current_done += delta
        if total:
            while len(self._stream_totals) <= stream_id:
                self._stream_totals.append(0)
            self._stream_totals[stream_id] = total
        self._flush_pending_line()
        self._maybe_emit()

    def update(self, downloaded, total):
        self.current_done = downloaded
        if total:
            self._stream_totals = [total]
        self._flush_pending_line()
        self._maybe_emit()

    def status(self, message):
        self.worker.phase.emit(message)  # phase 是 Qt 信号，必须用 .emit
        self.worker.milestone(LogCategory.NORMAL, message)

    def finish(self):
        # 兜底输出"正在下载"行（如缓存命中：无字节也无清晰度）
        self._flush_pending_line()
        q = f"[{self.current_quality.display_name}] " if self.current_quality else ""
        # 单文件完成。current_done == 0 且没收到任何字节 → 大概率命中本地缓存直接跳过
        if self.current_done == 0:
            self.worker.milestone(LogCategory.SUCCESS, f"已存在，跳过：{self.current_name}")
        else:
            self.worker.milestone(LogCategory.SUCCESS, f"下载完成：{q}{self.current_name}")

    def make_stream_callback(self):
        return self.update

    def iter_count(self):
        return range(1, self.n + 1)

    def _flush_pending_line(self):
        """输出"正在下载 第 i/n 个：[清晰度] 文件名"（每个文件只输出一次）。"""
        if not self._pending_line:
            return
        self._pending_line = False
        q = f"[{self.current_quality.display_name}] " if self.current_quality else ""
        idx = self._mono
        if self.n:
            self.worker.milestone(LogCategory.PROGRESS, f"正在下载 第 {idx}/{self.n} 个：{q}{self.current_name}")
        else:
            self.worker.milestone(LogCategory.PROGRESS, f"正在下载 第 {idx} 个：{q}{self.current_name}")

    def _grand_total(self):
        totals = [t for t in self._stream_totals if t]
        return sum(totals) if totals else None

    def _maybe_emit(self):
        if self.current_done - self._last_emitted < self._throttle:
            return
        self._last_emitted = self.current_done
        self.worker.progress.emit(self.current_done, self._grand_total() or 0)
