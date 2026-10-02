"""
带账本的自增文件名分配器（媒体资源）。

配合"动态下载"的媒体命名规则：``{动态发布日期}_{当日自增号}.{ext}``
（口径：**按日期重新计数**——每天第一张为 ``日期_1``，同日递增，跨日重置；
同一日期内编号只增不回退）。

多线程安全策略：
- **进程内共享实例**：同一目录的分配器必须经 :func:`get_asset_allocator`
  获取（共用一把锁、计数器与账本状态），避免多 worker 各自缓存计数器
  导致编号回退或账本互相覆盖；
- **预分配**：任务构建阶段（单线程）在锁内一次性发号，下载线程只消费
  已绑定路径，运行期不查询编号；
- **O_EXCL 原子占位**：分配时 `touch(exist_ok=False)` 占位，跨进程/崩溃
  残留冲突时自动顺延，避免撞名；
- **账本**（默认 ``index.json``）：``{key: {file, url, status}}`` + 各日期
  下一个编号 ``next_id``；分配即写 pending、下载成功改 done；重试/force
  复用原文件名，账本丢失时用目录扫描自愈（同日 ``max+1``）。
"""

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_FILE_ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d+)\.([A-Za-z0-9]+)$")


class AssetIdAllocator:
    """单个目录内的自增文件名分配器（每个媒体目录一个实例，见 get_asset_allocator）。"""

    def __init__(self, directory, ledger_path=None):
        self.directory = Path(directory)
        self.ledger_path = Path(ledger_path) if ledger_path is not None else self.directory / "index.json"
        self._lock = threading.Lock()
        self._ledger: Optional[dict] = None
        self._scanned_dates: set = set()

    # ---- 对外接口 ----

    def find(self, key) -> Optional[Path]:
        """按账本键查找已分配的文件路径；未分配返回 None。"""
        with self._lock:
            self._load_locked()
            entry = self._ledger["entries"].get(str(key))
            if not entry or not entry.get("file"):
                return None
            return self.directory / entry["file"]

    def allocate(self, key, date: str, ext: str, url: str = "") -> Path:
        """为 ``key`` 分配（或复用）一个文件路径；新分配立即写入账本（pending）。

        编号按 ``date`` 独立计数（当天已有最大号 + 1，跨日重置）；
        复用的前提是账本已有该 key 的记录（重试/force 不换号）。
        """
        ext = (ext or "jpg").lstrip(".").lower()
        key = str(key)
        with self._lock:
            self._load_locked()
            entry = self._ledger["entries"].get(key)
            if entry and entry.get("file"):
                return self.directory / entry["file"]
            self.directory.mkdir(parents=True, exist_ok=True)
            counter = self._counter_locked(date)
            while True:
                candidate = f"{date}_{counter}.{ext}"
                counter += 1
                path = self.directory / candidate
                try:
                    path.touch(exist_ok=False)  # O_EXCL 占位（跨进程兜底）
                except FileExistsError:
                    continue
                break
            self._ledger["next_id"][date] = counter
            self._ledger["entries"][key] = {"file": candidate, "url": url or "", "status": "pending"}
            self._flush_locked()
            return path

    def mark_done(self, key) -> None:
        """把 ``key`` 的账本状态更新为 done（文件已完整落盘）。"""
        key = str(key)
        with self._lock:
            self._load_locked()
            entry = self._ledger["entries"].get(key)
            if entry is None or entry.get("status") == "done":
                return
            entry["status"] = "done"
            self._flush_locked()

    # ---- 内部 ----

    def _load_locked(self) -> None:
        if self._ledger is not None:
            return
        ledger = {"next_id": {}, "entries": {}}
        if self.ledger_path.is_file():
            try:
                data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    entries = data.get("entries")
                    if isinstance(entries, dict):
                        ledger["entries"] = {
                            str(key): value
                            for key, value in entries.items()
                            if isinstance(value, dict)
                        }
                    next_map = data.get("next_id")
                    if isinstance(next_map, dict):
                        ledger["next_id"] = {
                            str(key): int(value)
                            for key, value in next_map.items()
                            if isinstance(value, (int, str)) and str(value).isdigit()
                        }
            except (ValueError, OSError) as exc:
                logger.warning("[AssetIdAllocator] 账本损坏，按目录扫描重建：%s", exc)
        self._ledger = ledger
        self._scanned_dates = set()

    def _counter_locked(self, date: str) -> int:
        """该日期的下一个可用编号：账本记录值与"目录内同日最大号 + 1"取较大者。

        账本值是已发号的历史（删除文件不回退）；目录扫描用于账本缺失时自愈。
        每个日期只扫描一次，之后走内存计数器。
        """
        counter = int(self._ledger["next_id"].get(date) or 0)
        if date not in self._scanned_dates:
            self._scanned_dates.add(date)
            counter = max(counter, self._scan_max_id(date) + 1)
        return counter

    def _scan_max_id(self, date: str) -> int:
        max_id = 0
        if self.directory.is_dir():
            for entry in self.directory.iterdir():
                match = _FILE_ID_RE.match(entry.name)
                if match and match.group(1) == date:
                    max_id = max(max_id, int(match.group(2)))
        return max_id

    def _flush_locked(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temp_path = self.ledger_path.with_name(self.ledger_path.name + ".tmp")
        temp_path.write_text(
            json.dumps(self._ledger, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            # Windows 上目标文件可能被短暂占用，os.replace 偶发 PermissionError，小步重试
            last_error: Optional[Exception] = None
            for attempt in range(5):
                try:
                    os.replace(temp_path, self.ledger_path)
                    return
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(0.05 * (attempt + 1))
            raise last_error  # type: ignore[misc]
        finally:
            temp_path.unlink(missing_ok=True)


# 进程内共享的分配器注册表：同一目录只保留一个实例（锁/计数器/账本状态共享）
_SHARED_ALLOCATORS: dict = {}
_SHARED_ALLOCATORS_LOCK = threading.Lock()


def get_asset_allocator(directory, ledger_path=None) -> AssetIdAllocator:
    """返回进程内共享的分配器实例（同一目录共用一个）。

    多线程 / 多 worker 批量下载同一个 UP 时，必须经由本函数获取分配器：
    若各 worker 各自 new 一个实例，计数器缓存互不可见（编号可能重复后再靠
    O_EXCL 顺延），账本写入也会互相覆盖（last-wins 丢失归属记录）。
    """
    key = str(Path(directory).resolve())
    with _SHARED_ALLOCATORS_LOCK:
        allocator = _SHARED_ALLOCATORS.get(key)
        if allocator is None:
            allocator = AssetIdAllocator(directory, ledger_path)
            _SHARED_ALLOCATORS[key] = allocator
        return allocator
