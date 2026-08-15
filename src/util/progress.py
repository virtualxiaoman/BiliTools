"""
批量下载进度显示。

格式：`[i/n] [名字] [清晰度]: a/bMB (p%)`
- `i`: 当前是第 i 个视频（1 起）
- `n`: 本次总共要下载的视频数
- `名字`: 目标文件名
- `清晰度`: 目标清晰度标签（如 `4K`、`1080P`），可选
- `a`: 当前已下载大小（MB）
- `b`: 总大小（MB），来自各流响应头 Content-Length 之和；无法获知时显示为当前已下载量
- `p`: 下载百分比；无法获知总大小时显示 `--`

单个视频由「视频流 + 音频流 + ffmpeg 合成」组成：
- 视频/音频流下载阶段：字节数通过 `add()` 增量累加（跨流累计，b = 各流总大小之和）；
- ffmpeg 合成阶段：无字节数，用 `status()` 单独提示。
"""

from typing import Callable, List, Optional
import threading

from src.models.download_model import VideoQuality

# 进度回调签名：已下载字节数, 总字节数（总字节数可能为 None）
StreamProgressCallback = Callable[[int, Optional[int]], None]


class BatchProgress:
    """跨多个视频的累计进度显示，配合 download_stream 的 progress_cb 使用。

    [使用方法]
        progress = BatchProgress(n=3, label="下载任务")
        for i in progress.iter_count():
            progress.start(i, filename)
            download_stream(url, path, progress_cb=progress.make_stream_callback())  # 单流
            # 或多流：用 delta 累加
            last = 0
            def cb(done, total):
                nonlocal last
                progress.add(done - last, total)
                last = done
            download_stream(url, path, progress_cb=cb)
            progress.status("正在合成...")
            merge_video_audio(...)
            progress.finish()
    """

    def __init__(self, n: int = 1, label: str = "下载", display: bool = True):
        """
        :param n: 本次要下载的视频总数
        :param label: 任务说明（start 时打印）
        :param display: 是否输出到 stdout（False 时静默）
        """
        self.n = max(n, 1)
        self.label = label
        self.display = display
        self.current_index = 0
        self.current_name = ""
        self.current_quality: Optional[VideoQuality] = None  # 当前视频的清晰度
        self.current_done = 0  # 当前视频累计已下载字节
        self._stream_totals: List[int] = []  # 各流已知的总大小

    # ---- 每个视频的生命周期 ----

    def start(self, index: int, name: str) -> None:
        """开始下载第 index 个视频（1 起），name 为目标文件名。"""
        self.current_index = index
        self.current_name = name
        self.current_quality = None
        self.current_done = 0
        self._stream_totals = []
        if self.display:
            print(f"\n{self._header()}: 准备下载")

    def set_quality(self, quality: VideoQuality) -> None:
        """设置当前视频的清晰度标签（在名称和 MB 进度之间显示，如 `[4K]`）。

        仅在已有下载进度时刷新渲染，避免设置标签瞬间打印一行空进度。
        """
        self.current_quality = quality
        if self.current_done > 0:
            self._render()

    def add(self, delta: int, total: Optional[int], stream_id: int = 0) -> None:
        """增量累加已下载字节数（跨多个流时使用，delta 为本次流内增量）。

        :param delta: 本次流内新增的已下载字节
        :param total: 当前流的总大小（Content-Length）
        :param stream_id: 流序号（0 起），同一流多次回调需传相同 id，
                          每个流的总大小只记录一次，避免重复累加
        """
        self.current_done += delta
        if total:
            while len(self._stream_totals) <= stream_id:
                self._stream_totals.append(0)
            self._stream_totals[stream_id] = total
        self._render()

    def update(self, downloaded: int, total: Optional[int]) -> None:
        """直接设置已下载字节数（单流场景，download_stream 的 progress_cb 转发）。"""
        self.current_done = downloaded
        if total:
            self._stream_totals = [total]
        self._render()

    def status(self, message: str) -> None:
        """输出非字节性的状态（如 ffmpeg 合成阶段）。"""
        if not self.display:
            return
        print(f"\r{self._header()}: {message}", flush=True)

    def finish(self) -> None:
        """当前视频完成，输出完成行。"""
        self._render(final=True)

    # ---- 渲染 ----

    def _header(self) -> str:
        """进度行前缀：`[i/n] [名字] [清晰度]`。"""
        parts = f"[{self.current_index}/{self.n}] [{self.current_name}]"
        if self.current_quality is not None:
            parts += f" [{self.current_quality.display_name}]"
        return parts

    def _grand_total(self) -> Optional[int]:
        """各流总大小之和（所有流都有 Content-Length 时返回，否则 None）。"""
        totals = [t for t in self._stream_totals if t]
        return sum(totals) if totals else None

    def _render(self, final: bool = False) -> None:
        if not self.display:
            return
        done_mb = self.current_done / (1024 * 1024)
        grand = self._grand_total()
        if grand:
            total_mb = grand / (1024 * 1024)
            pct = min(self.current_done / grand * 100, 100.0)
            line = f"{self._header()}: {done_mb:.1f}/{total_mb:.1f}MB ({pct:.1f}%)"
        else:
            line = f"{self._header()}: {done_mb:.1f}/{done_mb:.1f}MB (--%)"
        if final:
            print(f"\r{line}")  # \r 清掉上一行残留，然后换行
        else:
            print(f"\r{line}", end="", flush=True)

    # ---- 供 download_stream 使用 ----

    def make_stream_callback(self) -> StreamProgressCallback:
        """生成一个 progress_cb 传给 download_stream（单流场景）。"""
        return self.update

    # ---- 便捷 ----

    def iter_count(self) -> range:
        """返回 (1..n) 的序号，供外层遍历。"""
        return range(1, self.n + 1)


class ParallelBatchProgress:
    """线程安全的并发下载进度：多线程各自持有「当前文件」状态，字节进度跨线程聚合。

    与 `BatchProgress` 契约一致（start/set_quality/add/update/status/finish/
    make_stream_callback/iter_count），并发下多个线程调用互不干扰；
    `current_done`/`current_index` 等仅代表聚合视图。display=True 时 stdout 会交错，
    GUI 场景通常 display=False 并经前端适配器转发 Qt 信号。
    """

    def __init__(self, n: int = 1, label: str = "下载", display: bool = False):
        self.n = max(n, 1)
        self.label = label
        self.display = display
        self.current_index = 0
        self.current_name = ""
        self.current_quality: Optional[VideoQuality] = None
        self.current_done = 0
        self._lock = threading.Lock()
        self._states: dict = {}     # thread ident -> _ThreadFile
        self._mono = 0              # 文件序号（跨线程自增）
        self._done_done = 0         # 已完成文件的已下载字节
        self._done_total = 0        # 已完成文件的已知总大小
        self._stream_totals: List[int] = []  # 聚合视图：各活跃线程已知总大小

    def start(self, index: int, name: str) -> None:
        with self._lock:
            self._mono += 1
            self._states[threading.get_ident()] = _ThreadFile(name, self._mono)
            self.current_index = index
            self.current_name = name
        if self.display:
            print(f"\n[{index}/{self.n}] [{name}]: 准备下载")

    def set_quality(self, quality: VideoQuality) -> None:
        with self._lock:
            st = self._states[threading.get_ident()]
            st.quality = quality
            self.current_quality = quality

    def add(self, delta: int, total: Optional[int], stream_id: int = 0) -> None:
        with self._lock:
            st = self._states[threading.get_ident()]
            st.done += delta
            if total:
                while len(st.totals) <= stream_id:
                    st.totals.append(0)
                st.totals[stream_id] = total
            self._aggregate_locked()
            self._render_locked()

    def update(self, downloaded: int, total: Optional[int]) -> None:
        with self._lock:
            st = self._states[threading.get_ident()]
            st.done = downloaded
            if total:
                st.totals = [total]
            self._aggregate_locked()
            self._render_locked()

    def status(self, message: str) -> None:
        if self.display:
            print(f"\r{self._header()}: {message}", flush=True)

    def finish(self) -> None:
        with self._lock:
            st = self._states.pop(threading.get_ident(), None)
            if st is None:
                return
            self._done_done += st.done
            self._done_total += st.grand_total()
            self._aggregate_locked()
            self._render_locked(final=True)

    def make_stream_callback(self) -> StreamProgressCallback:
        return self.update

    def iter_count(self) -> range:
        return range(1, self.n + 1)

    # ---- 聚合与渲染 ----

    def _aggregate_locked(self) -> None:
        done = self._done_done
        totals: List[int] = []
        for st in self._states.values():
            done += st.done
            totals.extend(t for t in st.totals if t)
        self._stream_totals = totals
        self.current_done = done

    def _grand_total(self) -> Optional[int]:
        active = sum(self._stream_totals) if self._stream_totals else 0
        return self._done_total + active if (active or self._done_total) else None

    def _header(self) -> str:
        parts = f"[{self.current_index}/{self.n}] [{self.current_name}]"
        if self.current_quality is not None:
            parts += f" [{self.current_quality.display_name}]"
        return parts

    def _render_locked(self, final: bool = False) -> None:
        if not self.display:
            return
        done_mb = self.current_done / (1024 * 1024)
        grand = self._grand_total()
        if grand:
            total_mb = grand / (1024 * 1024)
            pct = min(self.current_done / grand * 100, 100.0)
            line = f"{self._header()}: {done_mb:.1f}/{total_mb:.1f}MB ({pct:.1f}%)"
        else:
            line = f"{self._header()}: {done_mb:.1f}/{done_mb:.1f}MB (--%)"
        if final:
            print(f"\r{line}")
        else:
            print(f"\r{line}", end="", flush=True)


class _ThreadFile:
    """单个线程的「当前文件」进度状态（ParallelBatchProgress 内部使用）。"""

    __slots__ = ("name", "seq", "done", "totals", "quality")

    def __init__(self, name: str, seq: int):
        self.name = name
        self.seq = seq
        self.done = 0
        self.totals: List[int] = []
        self.quality: Optional[VideoQuality] = None

    def grand_total(self) -> int:
        totals = [t for t in self.totals if t]
        return sum(totals) if totals else 0
