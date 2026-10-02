"""AssetIdAllocator 单元测试（不联网）：按日期计数、占位顺延、账本与并发。"""

import json
import threading
from pathlib import Path

from src.util.asset_allocator import AssetIdAllocator, get_asset_allocator


def _read_ledger(directory: Path) -> dict:
    return json.loads((directory / "index.json").read_text(encoding="utf-8"))


def test_numbering_resets_per_date(tmp_path):
    directory = tmp_path / "images"
    allocator = AssetIdAllocator(directory)

    first = allocator.allocate("1/img/1", "2026-09-21", "png")
    second = allocator.allocate("1/img/2", "2026-09-21", "JPG")
    third = allocator.allocate("2/img/1", "2026-10-02", "png")
    fourth = allocator.allocate("2/img/2", "2026-10-02", "png")

    assert first.name == "2026-09-21_1.png"
    assert second.name == "2026-09-21_2.jpg"
    assert third.name == "2026-10-02_1.png"  # 跨日期重置，第二天重新从 _1 开始
    assert fourth.name == "2026-10-02_2.png"
    assert all(path.is_file() for path in (first, second, third, fourth))

    ledger = _read_ledger(directory)
    assert ledger["next_id"] == {"2026-09-21": 3, "2026-10-02": 3}
    assert ledger["entries"]["1/img/1"]["status"] == "pending"


def test_reuse_by_key_and_mark_done(tmp_path):
    directory = tmp_path / "images"
    allocator = AssetIdAllocator(directory)

    first = allocator.allocate("k", "2026-09-21", "png")
    allocator.mark_done("k")
    again = allocator.allocate("k", "2026-09-21", "png")

    assert again == first
    assert _read_ledger(directory)["entries"]["k"]["status"] == "done"
    assert sorted(p.name for p in directory.glob("*.png")) == [first.name]
    assert allocator.find("k") == first
    assert allocator.find("missing") is None


def test_placeholder_conflict_shifts_to_next_id(tmp_path):
    directory = tmp_path / "images"
    directory.mkdir(parents=True)
    (directory / "2026-09-21_1.png").touch()  # 崩溃残留/其他进程占位

    path = AssetIdAllocator(directory).allocate("k", "2026-09-21", "png")

    assert path.name == "2026-09-21_2.png"


def test_numbering_never_rolls_back_and_scan_self_heals(tmp_path):
    directory = tmp_path / "images"
    allocator = AssetIdAllocator(directory)
    first = allocator.allocate("a", "2026-09-21", "png")
    first.unlink()  # 删除文件不回收编号

    second = allocator.allocate("b", "2026-09-21", "png")
    assert second.name == "2026-09-21_2.png"

    # 账本丢失 → 目录扫描自愈（同日 max+1）
    (directory / "index.json").unlink()
    third = AssetIdAllocator(directory).allocate("c", "2026-09-21", "png")
    assert third.name == "2026-09-21_3.png"


def test_counters_survive_ledger_reload(tmp_path):
    """同日期计数器由账本持久化：删除文件后重载实例也不回退。"""
    directory = tmp_path / "images"
    first = AssetIdAllocator(directory).allocate("a", "2026-09-21", "png")
    first.unlink()

    again = AssetIdAllocator(directory).allocate("b", "2026-09-21", "png")

    assert again.name == "2026-09-21_2.png"


def test_corrupt_ledger_is_rebuilt(tmp_path):
    directory = tmp_path / "images"
    directory.mkdir(parents=True)
    (directory / "index.json").write_text("{ not json", encoding="utf-8")
    (directory / "2026-09-21_7.png").touch()

    path = AssetIdAllocator(directory).allocate("k", "2026-09-21", "png")

    assert path.name == "2026-09-21_8.png"


def test_shared_allocator_singleton(tmp_path):
    """同一目录共享同一实例（并发 worker 共用锁与账本状态）。"""
    directory = tmp_path / "images"
    one = get_asset_allocator(directory)
    two = get_asset_allocator(directory)
    other = get_asset_allocator(tmp_path / "covers")

    assert one is two
    assert other is not one


def test_concurrent_allocate_produces_unique_names(tmp_path):
    directory = tmp_path / "images"
    allocator = AssetIdAllocator(directory)
    results = []
    errors = []

    def worker(worker_id: int) -> None:
        try:
            for index in range(5):
                results.append(allocator.allocate(f"w{worker_id}-{index}", "2026-09-21", "png"))
        except Exception as exc:  # pragma: no cover - 失败时供断言
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    names = [path.name for path in results]
    assert len(names) == len(set(names)) == 40
    ledger = _read_ledger(directory)
    assert ledger["next_id"]["2026-09-21"] == 41
    assert len(ledger["entries"]) == 40
