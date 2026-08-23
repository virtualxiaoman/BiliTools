# BiliTools 生产级代码审查报告

- **审查日期**：2026-08-23
- **审查范围**：`src/`、`frontend/pyside6/`、`tests/`、启动脚本及其直接调用链。
- **审查方式**：静态代码审查、编译检查、非网络单元测试。
- **初始审查结论**：整改前代码不应直接作为高并发、可被不可信输入调用的生产下载服务发布；本次已完成代码级修复并通过非网络回归测试，但真实网络、Windows ACL 和跨进程场景仍需部署环境验证。
- **P0 结论**：本次未发现必须定为 P0 的远程立即接管或数据毁灭问题。原报告列出的 P1 风险已实施对应代码修复；Cookie 的 Windows ACL 完整加固及跨进程下载锁仍属于部署前验证/加固项。

## 一、验证结果

### 构建与测试

```text
compileall: PASS
pytest -q -m 'not network': 202 passed, 27 deselected, 0 failed
```

整改后，原报告列出的 4 个回归项已处理：

1. 下载面板输入框高度已恢复为 34。
2. 合集测试已 patch 生产实际使用的 `get_season_by_sid`。
3. 下载器已使用 `.part` 临时文件和原子提交，续传服务器返回 200 时会直接覆盖临时文件而不会重复追加。
4. 非网络回归测试全部通过；pytest 仅报告因受限环境无法创建 `.pytest_cache` 的权限警告，不影响测试结果。

上述结果只覆盖本地编译和非网络测试；真实网络、Windows ACL、第三方 ffmpeg 进程以及跨进程文件锁仍需在目标部署环境中进行集成验证。

## 二、风险摘要

| 风险等级 | 数量 | 发布要求 |
|---|---:|---|
| P0 | 0 | 暂未发现 P0 |
| P1 | 7 | 发布前必须修复并补充回归测试 |
| P2 | 11 | 下一个版本必须修复；涉及安全边界的项应提前修复 |
| P3 | 3 | 应纳入质量门禁和后续迭代 |

## 三、详细问题

### 1. 下载失败污染正式文件，损坏文件会被误判为缓存

**问题位置** -> `G:\Projects\py\BiliTools\src\util\downloader.py:111-153`；调用方 `G:\Projects\py\BiliTools\src\services\video.py:391-411`、`455-477`

**风险等级** -> **P1-高**

**问题描述与影响** -> `download_stream()` 直接向最终文件写入。网络中断、进程崩溃、磁盘空间耗尽或 `QThread.terminate()` 发生时，目标路径会保留部分内容。`VideoService._find_downloaded_file()` 只依据 BV 号、扩展名和 P 序号判断存在，不验证文件大小、容器可读性或下载是否完成；下一次运行会返回 `cached=True`，把损坏媒体当成成功结果。多个任务同时命中同一目标时还会交错续传或覆盖。该问题会造成静默数据损坏，且用户通常只能在播放时才发现。

**修改建议与代码** -> 下载必须写入同目录 `.part` 文件，完成长度校验后使用 `os.replace()` 原子提交；正式文件只允许由成功提交产生。下面代码可直接替换现有 `download_stream()` 的实现主体；它同时处理 Range 被忽略、`Content-Range` 起点不匹配、提前 EOF、响应关闭和进程内同目标锁。跨进程场景仍需增加文件锁（例如 portalocker）。

```python
# src/util/downloader.py
import os
import threading
from pathlib import Path
from typing import Optional

import requests

from src.api.errors import DownloadError

_TARGET_LOCKS: dict[str, threading.Lock] = {}
_TARGET_LOCKS_GUARD = threading.Lock()


def _target_lock(path: Path) -> threading.Lock:
    key = str(path.resolve()).casefold()
    with _TARGET_LOCKS_GUARD:
        return _TARGET_LOCKS.setdefault(key, threading.Lock())


def _parse_content_range(value: str | None) -> tuple[int, int, int] | None:
    # 返回 (start, end, total)，无法解析时返回 None。
    if not value or not value.startswith("bytes "):
        return None
    try:
        range_part, total_part = value[6:].split("/", 1)
        start_text, end_text = range_part.split("-", 1)
        return int(start_text), int(end_text), int(total_part)
    except (ValueError, TypeError):
        return None


def download_stream(
    url: str,
    save_path: Path,
    headers: Optional[dict] = None,
    *,
    progress_cb=None,
    chunk_size: int = 1024 * 256,
    max_retries: int = 3,
    overwrite: bool = False,
) -> int:
    """以 .part 临时文件下载，成功后原子替换正式文件。"""
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = save_path.with_name(save_path.name + ".part")

    if chunk_size <= 0 or max_retries < 0:
        raise ValueError("chunk_size 必须为正数，max_retries 不能为负数")

    with _target_lock(save_path):
        if overwrite:
            save_path.unlink(missing_ok=True)
            part_path.unlink(missing_ok=True)

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            downloaded = part_path.stat().st_size if part_path.exists() else 0
            request_headers = dict(headers or {})
            if downloaded:
                request_headers["Range"] = f"bytes={downloaded}-"

            try:
                with requests.get(
                    url,
                    headers=request_headers,
                    stream=True,
                    timeout=(10, 60),
                ) as response:
                    response.raise_for_status()

                    if downloaded:
                        content_range = _parse_content_range(
                            response.headers.get("Content-Range")
                        )
                        if response.status_code != 206 or (
                            content_range is not None
                            and content_range[0] != downloaded
                        ):
                            # 服务器忽略 Range 或返回错误起点，必须从头开始。
                            part_path.unlink(missing_ok=True)
                            downloaded = 0
                            request_headers.pop("Range", None)
                            continue

                    content_length = int(
                        response.headers.get("Content-Length", "0")
                    ) or None
                    content_range = _parse_content_range(
                        response.headers.get("Content-Range")
                    )
                    expected_total = (
                        content_range[2]
                        if content_range is not None and content_range[2] >= 0
                        else (downloaded + content_length
                              if content_length is not None else None)
                    )

                    with part_path.open("ab" if downloaded else "wb") as output:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if not chunk:
                                continue
                            output.write(chunk)
                            downloaded += len(chunk)
                            if progress_cb is not None:
                                progress_cb(downloaded, expected_total)

                if expected_total is not None and downloaded != expected_total:
                    raise IOError(
                        f"下载不完整：{downloaded}/{expected_total} bytes"
                    )

                os.replace(part_path, save_path)
                return downloaded

            except (requests.RequestException, OSError, ValueError) as exc:
                last_error = exc
                if attempt >= max_retries:
                    break

        raise DownloadError(f"下载失败：{url}，原因：{last_error}") from last_error
```

另外，缓存命中前应至少检查正式文件 `stat().st_size > 0`；对 mp4/flv 建议在提交前增加容器解析校验。`.part` 文件不得被 `_find_downloaded_file()` 纳入扫描。

### 2. 并发下载可能共享同一个 `requests.Session`

**问题位置** -> `G:\Projects\py\BiliTools\src\services\video.py:811-819`、`1055-1068`；`G:\Projects\py\BiliTools\src\api\session.py:47-52`

**风险等级** -> **P1-高**

**问题描述与影响** -> `_account_services()` 在没有传入 `account_sessions` 时返回 `[self]`。当 `threads > 1`，所有 worker 共享同一个 `VideoService`、`BiliSession` 和底层 `requests.Session`。`requests.Session` 不应被当成线程安全的可变状态容器使用；headers、cookie、连接池及未来新增的 session 状态会出现竞态。更严重的是账号切换会改变全局 cookie 路径，导致并发任务读取到错误账号的凭证。

**修改建议与代码** -> 每个并发 worker 使用独立会话；会话构造时固定 cookie 路径，不要在后续请求时重新读取全局当前账号。将以下构造函数和服务工厂替换到对应文件，并将所有并发调用改为 `self._account_services(account_sessions, threads)`。

```python
# src/api/session.py
class BiliSession:
    def __init__(
        self,
        cookie_path: str | None = None,
        referer: str = "https://www.bilibili.com/",
        max_retry: int = MAX_RETRY,
        timeout: float = REQUEST_TIMEOUT,
    ):
        self.cookie_path = (
            str(cookie_path) if cookie_path is not None
            else str(get_cookie_path())
        )
        self.cookie = self._load_cookie(self.cookie_path)
        self.referer = referer
        self.max_retry = max_retry
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.cookie.to_headers(referer=referer))

    def close(self) -> None:
        self.session.close()
```

```python
# src/services/video.py

def _account_services(self, account_sessions=None, threads: int = 1) -> list:
    if account_sessions:
        # 调用方必须保证列表中的 session 对象互不相同；必要时可在这里按
        # cookie_path 去重并重新构造。
        return [
            VideoService(session=session, default_dir=self.default_dir)
            for session in account_sessions
        ]

    if threads <= 1:
        return [self]

    # 未启用多账号分流时，仍然为每个 worker 创建独立 requests.Session。
    return [
        VideoService(
            session=BiliSession(
                cookie_path=self.session.cookie_path,
                referer=self.session.referer,
                max_retry=self.session.max_retry,
                timeout=self.session.timeout,
            ),
            default_dir=self.default_dir,
        )
        for _ in range(threads)
    ]
```

批量函数结束后应在 `finally` 中关闭本次创建的 session；不要关闭由调用方传入且仍会复用的 session。并行测试应显式断言不同 worker 的 `id(service.session.session)` 不同。

### 3. 统一请求层对所有 POST 自动重试，可能重复提交写操作

**问题位置** -> `G:\Projects\py\BiliTools\src\api\session.py:105-121`

**风险等级** -> **P1-高**

**问题描述与影响** -> 当前 `_request()` 对 GET、POST 使用同一套重试循环。POST 遇到超时、连接断开或响应解析失败时，服务端可能已经执行成功，客户端却看不到响应；自动重试会重复发表评论、私信、签约、收藏或其他写操作。仅靠“网络异常才重试”不能保证安全，因为网络异常发生在服务端处理之后同样常见。

**修改建议与代码** -> 默认只重试 GET/HEAD/OPTIONS；POST 必须由调用方显式声明幂等，或携带服务端支持的幂等键。加入指数退避和 jitter，避免所有 worker 同步重试。

```python
# src/api/session.py
import random


def _request(
    self,
    method: str,
    url: str,
    *,
    retryable: bool | None = None,
    **kwargs,
) -> dict:
    method = method.upper()
    if retryable is None:
        retryable = method in {"GET", "HEAD", "OPTIONS"}

    headers = kwargs.pop("headers", None)
    if headers:
        merged = dict(self.session.headers)
        merged.update(headers)
        kwargs["headers"] = merged

    last_error: Exception | None = None
    attempts = self.max_retry if retryable else 0
    for attempt in range(attempts + 1):
        try:
            with self.session.request(
                method,
                url,
                timeout=self.timeout,
                **kwargs,
            ) as response:
                response.raise_for_status()
                payload = response.json()
                raise_for_code(
                    payload.get("code", 0),
                    payload.get("message", ""),
                )
                return payload["data"]
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            logger.warning(
                "[BiliSession-%s] 第%d次请求%s失败：%s",
                method, attempt + 1, url, exc,
            )
            if attempt >= attempts:
                break
            delay = RETRY_DELAY * (2 ** attempt)
            time.sleep(delay + random.uniform(0, 0.25))

    raise last_error or RuntimeError(f"请求失败：{url}")
```

非幂等写操作必须显式关闭重试：

```python
session.post(url, data=data, retryable=False)
```

更稳妥的做法是为服务端支持的写操作生成幂等键，并在服务端按键去重；客户端不能凭空假设 POST 幂等。

### 4. 应用退出时 `QThread.terminate()` 可能破坏文件和 ffmpeg 输出

**问题位置** -> `G:\Projects\py\BiliTools\frontend\pyside6\workers\download_manager.py:34-51`

**风险等级** -> **P1-高**

**问题描述与影响** -> `requestInterruption()` 只是设置 Qt 线程标志，当前下载循环、`requests.get()` 和 `subprocess.run()` 都没有检查该标志；等待超时后直接调用 `terminate()` 强杀 Python 线程。强杀可能发生在文件写入、ffmpeg 输出、临时目录替换或 Python finally 尚未执行时，造成句柄泄漏、临时文件残留、正式文件损坏和 Qt 对象状态不一致。注释中“中断不会损坏已有数据”与实现不符。

**修改建议与代码** -> 加入协作式取消事件；下载循环每块检查事件，ffmpeg 用 `Popen` 轮询并在取消时终止子进程；退出时取消、等待，不调用 `terminate()`。下面是 `DownloadManager.shutdown()` 的可直接替换版本，前提是 `DownloadWorker.cancel()` 实现为设置 `threading.Event`，并由底层下载/合成函数读取该事件。

```python
# frontend/pyside6/workers/download_manager.py
import logging
import time

logger = logging.getLogger(__name__)


def shutdown(self, wait_ms: int = 2000) -> None:
    workers = list(self._tasks.values())
    for worker in workers:
        try:
            worker.cancel()  # 设置取消 Event；不是 QThread.terminate()
        except Exception:
            logger.exception("取消下载任务失败")

    deadline = time.monotonic() + wait_ms / 1000.0
    for worker in workers:
        remaining = max(0, int((deadline - time.monotonic()) * 1000))
        if worker.isRunning():
            worker.wait(remaining)

    still_running = [worker for worker in workers if worker.isRunning()]
    if still_running:
        # 不破坏正在写入的任务；交由应用自然退出/操作系统回收，正式文件只能
        # 由 .part -> replace 产生，因此未完成任务不会伪装成缓存。
        logger.error(
            "仍有 %d 个下载任务未能优雅停止；未调用 QThread.terminate()",
            len(still_running),
        )
```

`DownloadWorker` 至少应有：

```python
self._cancel_event = threading.Event()

def cancel(self) -> None:
    self._cancel_event.set()

def is_cancelled(self) -> bool:
    return self._cancel_event.is_set() or self.isInterruptionRequested()
```

所有网络读取和 ffmpeg 调用必须使用短连接/读取超时；取消时只能留下 `.part`，不能覆盖正式目标。

### 5. 账号表和登录 Cookie 持久化存在并发覆盖、崩溃损坏和权限风险

**问题位置** -> `G:\Projects\py\BiliTools\src\services\account.py:72-85`、`105-151`、`210-229`；`src/config/path.py`、`src/config/cookie.py`

**风险等级** -> **P1-高**

**问题描述与影响** -> `accounts.json` 使用固定名称 `accounts.json.tmp`，多个 `AccountManager` 或登录流程同时保存会互相覆盖；写入没有 `flush/fsync`，进程崩溃可能留下半个文件。登录 Cookie 使用 `write_text()` 直接写正式路径，同样存在半写入状态。Cookie 含 `SESSDATA`/`bili_jct`，文件权限没有在代码中明确收紧；本机其他用户、备份程序或恶意进程获得文件后可劫持登录会话并执行写操作。

**修改建议与代码** -> 使用同目录唯一临时文件、flush + fsync、原子替换、最小权限；多进程更新仍必须在读-改-写整个事务外加跨进程锁，否则只能避免“半文件”，不能避免 lost update。以下函数可直接放入 `src/services/account.py`，同时用于账号表和 Cookie。

```python
# src/services/account.py
import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str, mode: int = 0o600) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    tmp = Path(tmp_name)
    try:
        try:
            os.chmod(tmp, mode)
        except OSError:
            pass
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            fd = -1
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        try:
            os.chmod(path, mode)
        except OSError:
            pass
    finally:
        if fd != -1:
            os.close(fd)
        tmp.unlink(missing_ok=True)
```

替换保存和登录写入：

```python
# AccountManager.save()
atomic_write_text(
    self.accounts_file,
    json.dumps(data, ensure_ascii=False, indent=2),
    mode=0o600,
)

# AccountManager.handle_login()
atomic_write_text(save_path, set_cookie.strip(), mode=0o600)
```

Windows 上还需使用 ACL/`icacls` 或 `CreateFile` 实现“仅当前用户可读”和跨进程锁；POSIX 上的 `0o600` 不能替代 Windows ACL。写入前必须校验 `mid`、Cookie 必需字段和 JSON schema，拒绝使用 `mid=0` 作为永久账号标识。

### 6. 自定义文件名可路径穿越并覆盖任意可写文件

**问题位置** -> `G:\Projects\py\BiliTools\src\services\video.py:405-411`、`470-477`、`548-554`、`641-648`；`G:\Projects\py\BiliTools\src\util\filename.py:93-97`

**风险等级** -> **P1-高**

**问题描述与影响** -> `save_dir / filename` 和 `resolve_save_path()` 没有拒绝绝对路径、盘符、UNC 路径或 `..`。只要调用方能控制 `filename`，就能把媒体内容写入保存目录之外，覆盖配置、脚本、启动项或其他可写文件。即使当前 GUI 未暴露全部自定义文件名入口，后端服务/API 仍是安全边界，不能依赖 UI 限制。

**修改建议与代码** -> 对自定义文件名只允许单层文件名，不允许任何路径分隔符；解析后必须仍位于保存目录内。将 `resolve_save_path()` 替换为：

```python
# src/util/filename.py
from pathlib import Path


def resolve_save_path(directory, filename: str) -> Path:
    if not isinstance(filename, str) or not filename:
        raise ValueError("filename 必须是非空字符串")

    directory = Path(directory).expanduser().resolve()
    raw = Path(filename)
    if (raw.is_absolute() or raw.name != filename or
            any(separator in filename for separator in ("/", "\\")) or
            filename in {".", ".."}):
        raise ValueError("filename 必须是单层文件名，禁止绝对路径和路径穿越")

    candidate = (directory / raw).resolve()
    if candidate.parent != directory:
        raise ValueError("filename 超出保存目录")
    directory.mkdir(parents=True, exist_ok=True)
    return candidate
```

视频服务的每一个 `save_dir / filename` 也必须改为调用该函数；不能只修复一个入口。

### 7. Cookie 明文保存，账号会话缺少安全存储边界

**问题位置** -> `G:\Projects\py\BiliTools\src\config\path.py`、`src\config\cookie.py`、`G:\Projects\py\BiliTools\src\services\account.py:223`、`G:\Projects\py\BiliTools\src\services\login.py:206`

**风险等级** -> **P1-高**

**问题描述与影响** -> Cookie 文件本身就是 bearer credential。当前设计将原始 `Set-Cookie` 长期落盘，且没有统一权限收紧、密钥环/凭证库或安全擦除策略。发生恶意软件、低权限同机用户、备份泄露或日志/诊断包外带时，会话可被直接复用；`bili_jct` 还可能让攻击者执行账号写操作。该问题与上一个“原子写入”不同：原子写入解决完整性，本项解决机密性。

**修改建议与代码** -> 首选 Windows Credential Manager、macOS Keychain、Linux Secret Service；如果项目必须兼容纯文件模式，至少使用用户私有目录、ACL/`0o600`、权限启动检查、禁止把 Cookie 打入日志，并提供注销时删除凭证。读取路径和 Cookie 值都不得出现在异常摘要、任务描述或诊断导出中。

```python
# 文件模式的最低门槛；Windows 还必须补充 ACL 设置。
import os
from pathlib import Path

def ensure_private_file(path: Path) -> None:
    if path.exists():
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        if os.name != "nt" and (path.stat().st_mode & 0o077):
            raise PermissionError(f"Cookie 文件权限过宽：{path}")

# 在读取 Cookie 前调用；写入完成后也调用一次。
ensure_private_file(cookie_path)
```

### 8. 缓存查找对每个下载项递归扫描整个目录，批量场景趋向 O(N²)

**问题位置** -> `G:\Projects\py\BiliTools\src\services\video.py:332-363`，尤其 `346-361`

**风险等级** -> **P2-中**

**问题描述与影响** -> 每个视频下载前都对每个缓存根执行 `rglob("*")`。当目录有 N 个文件、批量任务有 M 个视频时，最坏情况下会重复遍历约 M×N 个目录项，还会把 `.part`、无关文件和嵌套目录纳入扫描。网络请求可能尚未发生，CPU、磁盘 IO 和 UI 响应已经被拖慢。

**修改建议与代码** -> 优先根据确定性文件名直接检查；若要兼容旧文件，启动时一次性建立 `bvid/page/ext -> Path` 索引并增量更新，或至少限制文件名模式和目录深度。

```python
candidate = save_dir / self._default_filename(info, bvid, page, ext)
if candidate.is_file() and candidate.stat().st_size > 0:
    return candidate
# 兼容旧缓存时再做一次受限扫描，且显式忽略 .part/.tmp。
```

### 9. 下载、合成和批量流程没有统一 `finally` 清理进度状态

**问题位置** -> `G:\Projects\py\BiliTools\src\services\video.py:413-429`、`479-489`、`556-605`、`694-719`、`785-809`；`src/util/downloader.py:144-153`

**风险等级** -> **P2-中**

**问题描述与影响** -> 多个路径只在成功分支调用 `progress.finish()`。请求失败、ffmpeg 失败、缓存异常或模型解析异常时，状态对象可能留在 `BatchProgress`/`ParallelBatchProgress` 内部，GUI 进度停在“进行中”，后续任务的总数、完成数和日志也会错误。长时间运行会形成状态对象累积。

**修改建议与代码** -> 每个任务使用 `try/except/finally`，成功时 finish，失败时调用明确的 `fail()`/`cancel()` 并删除线程状态；不要用“返回缓存结果”掩盖异常。

```python
try:
    result = self._download_one(...)
except Exception:
    progress.fail(item_id)  # 若当前类没有 fail，应新增并清理 _states
    raise
else:
    progress.finish(item_id)
finally:
    progress.remove(item_id)  # 或由 finish/fail 内部保证幂等清理
```

### 10. 封面下载一次性读入内存，且非原子、无大小和类型限制

**问题位置** -> `G:\Projects\py\BiliTools\src\api\session.py:79-87`；`G:\Projects\py\BiliTools\src\services\video.py:637-661`

**风险等级** -> **P2-中**

**问题描述与影响** -> `get_raw()` 返回 `resp.content`，封面下载再一次性写盘。远端响应大小没有上限，异常 CDN、恶意替换或批量任务会造成瞬时内存峰值；直接写正式图片路径会留下半个文件并被下一次存在性检查误判为缓存。

**修改建议与代码** -> 使用 `with response` + `iter_content()`，限制最大字节数，校验允许的 `Content-Type` 与图片 magic bytes，写 `.part` 后原子替换。`get_raw()` 不应承担大对象下载；它至少应增加 `max_bytes` 并在超限前终止。

### 11. WBI 密钥请求无 timeout/统一重试，缓存读写无锁且无 TTL

**问题位置** -> `G:\Projects\py\BiliTools\src\api\auth.py:20-21`、`83-101`

**风险等级** -> **P2-中**

**问题描述与影响** -> `_get_wbi_keys()` 直接调用 `requests.get()`，没有连接/读取超时、重试上限或响应结构校验。首次并发调用会重复请求；普通全局变量在多线程下可能被同时初始化或清空。密钥长期缓存，服务端轮换后会持续签名失败，导致下载任务集体失败。

**修改建议与代码** -> 加 `timeout=(10, 30)`、有限指数退避和锁；缓存同时记录获取时间，TTL 到期刷新；收到明确签名失败/403 时清缓存并只重试一次；对 `wbi_img`、URL、key 长度做 schema 校验。

```python
_WBI_LOCK = threading.Lock()
_WBI_CACHE: tuple[str, str, float] | None = None
_WBI_TTL = 3600


def _get_wbi_keys():
    global _WBI_CACHE
    with _WBI_LOCK:
        now = time.monotonic()
        if _WBI_CACHE and now - _WBI_CACHE[2] < _WBI_TTL:
            return _WBI_CACHE[:2]
        with requests.get(
            f"{API_BASE}/x/web-interface/nav",
            headers={"User-Agent": UserAgent().pcChrome,
                     "Referer": "https://www.bilibili.com/"},
            timeout=(10, 30),
        ) as resp:
            resp.raise_for_status()
            payload = resp.json()
        wbi = payload.get("data", {}).get("wbi_img", {})
        img_url, sub_url = wbi.get("img_url"), wbi.get("sub_url")
        if not isinstance(img_url, str) or not isinstance(sub_url, str):
            raise ValueError("WBI 响应缺少 img_url/sub_url")
        img_key = img_url.rsplit("/", 1)[-1].split(".", 1)[0]
        sub_key = sub_url.rsplit("/", 1)[-1].split(".", 1)[0]
        if not img_key or not sub_key:
            raise ValueError("WBI key 为空")
        _WBI_CACHE = (img_key, sub_key, now)
        return img_key, sub_key
```

### 12. 输入短链解析可被利用为 SSRF/内网探测

**问题位置** -> `G:\Projects\py\BiliTools\frontend\pyside6\utils.py:77-84`、`97-117`

**风险等级** -> **P2-中**

**问题描述与影响** -> `follow_redirect()` 接受任意用户输入的 HTTP(S) URL，自动跟随全部重定向，没有主机白名单、重定向上限、DNS/IP 校验或 localhost/私网拦截。桌面应用攻击面低于服务端，但恶意任务文件、插件或远程控制场景可以借此探测内网服务，甚至访问云元数据地址。

**修改建议与代码** -> 只允许 `b23.tv`、`bilibili.com` 及明确的官方 CDN 域名；手动跟随重定向，每跳校验 hostname 解析到的 IP，拒绝 loopback、private、link-local、reserved、multicast，并设置最多 3 跳。若不需要任意 URL，直接拒绝非 B 站域名。

### 13. 请求响应对象没有统一显式关闭，连接池可能耗尽

**问题位置** -> `G:\Projects\py\BiliTools\src\api\session.py:79-87`、`src/util/downloader.py:119-143`、`src/api/auth.py:94-100`

**风险等级** -> **P2-中**

**问题描述与影响** -> `get_raw()`、媒体下载和 WBI 请求没有统一使用响应上下文管理器。高并发或异常分支下，响应体和底层连接不能及时回收到连接池，导致文件描述符、socket 和连接池槽位持续占用。

**修改建议与代码** -> 所有请求都使用 `with session.request(...) as response:` 或 `with requests.get(...) as response:`；流式下载在上下文内部完成；`BiliSession.close()` 必须由 worker 生命周期调用。不要让服务对象持有未关闭的临时 Session。

### 14. `get_playurl()` 过度信任 API 结构，降级响应会产生未诊断的 KeyError

**问题位置** -> `G:\Projects\py\BiliTools\src\services\video.py:164-184`

**风险等级** -> **P2-中**

**问题描述与影响** -> 代码直接读取 `data["dash"]["video"]` 和 `data["dash"]["audio"]`，没有处理 DASH 不可用、权限不足、接口返回 durl、字段为空或字段类型错误的情况。用户只会得到 `KeyError`/`TypeError`，无法区分“账号无权限”“视频无 DASH”“接口契约变化”，重试也不能解决。

**修改建议与代码** -> 先做 schema 校验，再把不同情况映射为明确的业务异常；允许明确的 durl 回退，不要静默把结构错误当成空列表。

```python
dash = data.get("dash") if isinstance(data, dict) else None
if not isinstance(dash, dict):
    raise BiliAPIError("播放接口未返回 DASH 数据，可能是权限不足或接口降级")
videos_raw = dash.get("video")
audios_raw = dash.get("audio")
if not isinstance(videos_raw, list) or not isinstance(audios_raw, list):
    raise BiliAPIError("播放接口 DASH 字段格式异常")
```

### 15. 多 P 封面下载循环重复下载同一个封面

**问题位置** -> `G:\Projects\py\BiliTools\src\services\video.py:637-648`、`710-712`

**风险等级** -> **P2-中**

**问题描述与影响** -> `download_all_pages(media_type="cover")` 按每个 P 循环，但 `download_cover()` 不接收 page，也没有按 P 选择封面 URL。多 P 视频会重复请求和覆盖/返回同一封面，结果列表包含重复项，进度总数与实际工作不符。

**修改建议与代码** -> 明确语义：视频封面是稿件级资源时只下载一次并禁止按 P 循环；如果产品需要分 P 封面，必须从 API 读取每 P 的封面字段并把 `page` 纳入文件名和缓存键。

### 16. `media_type` 未严格校验，拼写错误会悄悄触发大流量合成下载

**问题位置** -> `G:\Projects\py\BiliTools\src\services\video.py:702-717`、`790-806`

**风险等级** -> **P2-中**

**问题描述与影响** -> 未知 `media_type` 默认落入 `video_with_audio` 分支。调用方将 `video_with_audo` 等拼写错误传入时，程序不会立即报错，而是下载视频和音频并执行 ffmpeg，浪费带宽、磁盘和 CPU，且行为违反调用契约。

**修改建议与代码** -> 所有公共入口统一校验：

```python
_ALLOWED_MEDIA_TYPES = {"video", "audio", "video_with_audio", "cover"}
if media_type not in _ALLOWED_MEDIA_TYPES:
    raise ValueError(
        f"不支持的 media_type={media_type!r}，"
        f"允许值：{sorted(_ALLOWED_MEDIA_TYPES)}"
    )
```

### 17. 账号配置读取缺少 schema 校验，坏记录会中断启动

**问题位置** -> `G:\Projects\py\BiliTools\src\services\account.py:40-66`

**风险等级** -> **P2-中**

**问题描述与影响** -> 代码只捕获 JSON 解码和 IO 异常，却默认顶层一定是 dict、`accounts` 一定是列表、每项一定是 dict、`mid` 一定可转 int。手工编辑、旧版本迁移或部分损坏后会出现 `AttributeError`、`TypeError`、`ValueError`，直接阻断 GUI 启动。错误记录也没有保留原始文件供恢复。

**修改建议与代码** -> 对顶层和每条记录做类型/字段校验；坏项记录 warning 并跳过，原文件先复制为带时间戳的备份；`current_mid/default_mid` 必须验证为合法整数且存在于账号集合。

### 18. Cookie 缓存与账号切换存在全局状态竞态

**问题位置** -> `G:\Projects\py\BiliTools\src\api\auth.py:20-21`；`G:\Projects\py\BiliTools\src\config\cookie.py:39-40`、`74-117`；`G:\Projects\py\BiliTools\src\services\account.py:_apply_current`

**风险等级** -> **P2-中**

**问题描述与影响** -> Cookie/WBI 使用模块级可变缓存，账号切换会清理缓存并改变全局生效路径；并发构造 `BiliSession` 时可能在“路径切换、缓存清除、读取文件”之间穿插，造成 session 使用旧账号或新账号的非确定组合。该问题会放大第 2 项的会话共享风险。

**修改建议与代码** -> `BiliSession` 构造时固定 cookie 文件路径并读取不可变快照；账号切换、路径更新和缓存清理置于同一进程锁内。禁止服务层在每个请求时重新查询全局当前 Cookie 路径。

### 19. 自动进度输出与测试契约不一致

**问题位置** -> `G:\Projects\py\BiliTools\src\services\video.py:224-234`、`src/util/progress.py`；`tests/test_progress.py::TestAutoProgress::test_download_video_with_audio_auto_progress`

**风险等级** -> **P3-低**

**问题描述与影响** -> 当前自动进度行为没有产生测试要求的 `[1/1]` 输出。单文件调用、批量调用和 GUI 适配器对“完成”事件的语义不统一，用户可能看不到完成状态，测试也无法作为回归门禁。

**修改建议与代码** -> 明确 `BatchProgress(display=True)` 的默认契约；为自动创建的 progress 使用 `try/finally`；补充成功、缓存、失败、取消四条测试，并统一输出格式。修复实现或更新测试只能二选一，不能保留当前不一致状态。

### 20. GUI 输入框高度发生可见回归

**问题位置** -> `G:\Projects\py\BiliTools\frontend\pyside6\widgets\download_panel.py`；`tests/test_dressup_panel.py:65`、`78`

**风险等级** -> **P3-低**

**问题描述与影响** -> 当前输入框高度为 38，而设计/测试契约要求 34。该回归可能导致多 tab 布局溢出、按钮下移或小分辨率下可用空间减少。

**修改建议与代码** -> 若设计要求仍为 34，统一 `setFixedHeight(34)` 并更新样式边距；若 38 是新设计，则同步修改测试并在 Windows 高 DPI 下做截图回归。

### 21. 合集测试 mock 方法名与生产 API 不一致

**问题位置** -> 生产 `G:\Projects\py\BiliTools\src\services\video.py:735`；`tests/test_models.py::TestFetchSeason::test_season_id_builds_episodes`

**风险等级** -> **P3-低**

**问题描述与影响** -> 生产调用 `ArchiveService.get_season_by_sid()`，测试 mock `get_season_by_id()`。由于 MagicMock 会继续传播，测试没有验证真实的合集数据组装，反而暴露为失败。该问题削弱测试对合集下载逻辑的保护。

**修改建议与代码** -> 统一一个公开方法名；推荐保留 `get_season_by_sid()` 并让测试 patch 同名方法，同时用真实 `VideoSeason`/episode fixture 断言 bvid、cid、page 和标题，而不是只断言 mock 被调用。

## 四、必须追加的测试

1. 下载在第 N 个 chunk 抛 `ConnectionError` 后，正式文件不存在或仍是旧的完整文件，只有 `.part` 增长。
2. Range 服务器返回 200、错误 `Content-Range`、提前 EOF、错误 `Content-Length` 时均不能返回成功。
3. 两个线程同时下载同一目标，只产生一个正式文件，且内容 hash 正确。
4. `threads > 1` 时每个 worker 的 `requests.Session` 身份不同；账号 Cookie 不发生交叉。
5. 非幂等 POST 失败后只发送一次；显式幂等 GET/POST 才允许重试，并验证退避次数。
6. shutdown/cancel 在网络读和 ffmpeg 合成期间只留下 `.part`，不会产生损坏正式文件，也不会调用 `QThread.terminate()`。
7. 并发 `AccountManager.save()` 的结果可解析，且不会丢失另一个实例已提交的账号；Cookie 文件权限和 Windows ACL 均有测试。
8. 文件名为 `..\\config.ini`、`C:\\x`、`\\\\server\\share\\x`、`/tmp/x` 时全部拒绝。
9. SSRF 测试覆盖 localhost、RFC1918、link-local、IPv6 loopback、重定向到内网和超过最大跳转。
10. `get_playurl()` 覆盖无 dash、空 video/audio、durl 降级和字段类型异常。

## 五、整改优先级

### 发布前（P1）

1. 原子下载与正式文件完整性校验。
2. 并发会话隔离和账号路径快照。
3. 禁止对非幂等 POST 自动重试。
4. 协作式取消，移除 `QThread.terminate()`。
5. 账号表/Cookie 原子持久化、锁和权限控制。
6. 拒绝自定义文件名路径穿越。
7. Cookie 迁移到系统凭证库或至少实施严格 ACL。

### 下一迭代（P2）

缓存索引、响应流式限制、WBI TTL/锁、SSRF 防护、统一响应关闭、API schema 校验、media_type 校验、进度状态 finally 清理，以及多 P 封面语义修正。

### 质量门禁（P3）

修复自动进度、UI 尺寸和合集 mock 契约；将 `compileall`、非网络测试、静态类型检查、依赖漏洞扫描和关键下载集成测试纳入 CI。

## 六、最终审查结论

当前代码的主要生产风险不是“某个 if 写得多”，而是边界契约没有被强制执行：未完成文件可伪装成缓存、非幂等写请求可能被重放、线程共享可变会话、强制杀线程和明文凭证共同构成发布阻断项。必须先完成全部 P1 修复并通过新增回归测试，再考虑扩大并发规模或开放任意 SDK 调用方。