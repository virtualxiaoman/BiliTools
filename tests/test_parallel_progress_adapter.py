"""ParallelProgressAdapter（并发进度 → Qt 信号）的单元测试。

使用假 worker 模拟 Qt 信号对象，无需真实 QApplication/事件循环。
"""

import threading

from frontend.pyside6.signals import LogCategory
from frontend.pyside6.workers.progress_adapter import ParallelProgressAdapter


class _FakeSignal:
    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)


class _FakeWorker:
    def __init__(self):
        self.progress = _FakeSignal()
        self.phase = _FakeSignal()
        self.milestones = []

    def milestone(self, cat, text):
        self.milestones.append((cat, text))


def test_aggregates_bytes_across_threads():
    worker = _FakeWorker()
    adapter = ParallelProgressAdapter(4, "测试", worker)

    def run():
        adapter.start(1, "a.mp4")
        adapter.add(5_000_000, 10_000_000, stream_id=0)
        adapter.finish()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 每线程一条"下载完成"里程碑
    done_lines = [text for cat, text in worker.milestones if cat == LogCategory.SUCCESS]
    assert len(done_lines) == 2
    # 每线程一条"正在下载"里程碑
    start_lines = [text for cat, text in worker.milestones if cat == LogCategory.PROGRESS]
    assert len(start_lines) == 2
    # 进度信号聚合：done 为 2×5MB
    last_progress = worker.progress.calls[-1]
    assert last_progress[0] == 10_000_000


def test_per_thread_file_state_isolated():
    worker = _FakeWorker()
    adapter = ParallelProgressAdapter(2, "测试", worker)
    names = {}

    def run(tag):
        adapter.start(1, f"{tag}.mp4")
        adapter.add(1, None, stream_id=0)
        with adapter._lock:
            st = adapter._states[threading.get_ident()]
            names[tag] = (st.name, st.done)
        adapter.finish()

    threads = [threading.Thread(target=run, args=(t,)) for t in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert names == {"a": ("a.mp4", 1), "b": ("b.mp4", 1)}
