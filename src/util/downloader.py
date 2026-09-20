"""
下载工具：DASH 流的下载与音视频合成。

- `download_stream`     下载单个媒体流到本地文件（流式写入，支持进度回调）；
- `merge_video_audio`   合成音视频到单文件（subprocess 列表参数，避免 shell 注入）；
- `ffmpeg_available`    合成后端可用性探测（带缓存）。

合成后端按优先级探测：系统 PATH 中的 ffmpeg → imageio-ffmpeg 库内置的静态 ffmpeg
（pip 依赖，wheel 自带二进制，无需手动安装 ffmpeg）。

由旧 `src/utils.py` 的 `merge_video_audio`（os.system 拼接）迁移并加固而来。
"""

import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from src.api.errors import DownloadError, FFmpegNotFoundError

logger = logging.getLogger(__name__)

# 进度回调签名：已下载字节数, 总字节数（总字节数可能为 None/0）
ProgressCallback = Callable[[int, Optional[int]], None]

# 合成后端探测结果缓存（避免每次调用都执行 which / 导入 imageio）
_ffmpeg_checked: bool = False
_ffmpeg_path: Optional[str] = None

_TARGET_LOCKS: dict[str, threading.Lock] = {}
_TARGET_LOCKS_GUARD = threading.Lock()


def _target_lock(path: Path) -> threading.Lock:
    key = str(path.resolve()).casefold()
    with _TARGET_LOCKS_GUARD:
        return _TARGET_LOCKS.setdefault(key, threading.Lock())


def _parse_content_range(value: str | None) -> tuple[int, int, Optional[int]] | None:
    """解析 ``Content-Range``，允许总长度为 ``*``。"""
    if not isinstance(value, str) or not value.startswith("bytes "):
        return None
    try:
        range_part, total_part = value[6:].split("/", 1)
        start_text, end_text = range_part.split("-", 1)
        start, end = int(start_text), int(end_text)
        if start < 0 or end < start:
            return None
        total = None if total_part == "*" else int(total_part)
        if total is not None and (total <= end or total <= 0):
            return None
        return start, end, total
    except (ValueError, TypeError):
        return None


def _close_response(response) -> None:
    """关闭 requests 响应，同时兼容最小化的测试 double。"""
    close = getattr(response, "close", None)
    if callable(close):
        close()


def _imageio_ffmpeg_path() -> Optional[str]:
    """imageio-ffmpeg 库内置的静态 ffmpeg 可执行文件路径（未安装时返回 None）。

    imageio-ffmpeg 的 wheel 自带 ffmpeg 二进制，无需系统安装 ffmpeg，也无需
    运行时下载。仅在系统没有 ffmpeg 时才会被用到（懒加载，不拖累已有 ffmpeg 的机器）。
    """
    try:
        import imageio_ffmpeg
    except ImportError:
        return None
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        logger.warning("[downloader] 无法定位 imageio-ffmpeg 内置的 ffmpeg 可执行文件", exc_info=True)
        return None


def _resolve_ffmpeg() -> Optional[str]:
    """按优先级探测可用的 ffmpeg 可执行文件路径（结果缓存，仅探测一次）。

    1. 系统 PATH 中的 ffmpeg；
    2. imageio-ffmpeg 库内置的静态 ffmpeg（pip 依赖，wheel 自带二进制）。

    找不到时返回 None。
    """
    global _ffmpeg_checked, _ffmpeg_path
    if not _ffmpeg_checked:
        _ffmpeg_checked = True
        _ffmpeg_path = shutil.which("ffmpeg") or _imageio_ffmpeg_path()
    return _ffmpeg_path


def ffmpeg_available() -> bool:
    """检查音视频合成后端是否可用（系统 ffmpeg 或 imageio-ffmpeg，结果缓存）。"""
    return _resolve_ffmpeg() is not None


def download_stream(
    url: str,
    save_path: Path,
    headers: Optional[dict] = None,
    *,
    progress_cb: Optional[ProgressCallback] = None,
    chunk_size: int = 1024 * 256,
    max_retries: int = 3,
    overwrite: bool = False,
    cancel_event: Optional[threading.Event] = None,
) -> int:
    """下载到同目录 ``.part`` 文件，成功后原子替换正式文件。

    正式文件不会在新下载失败时被删除或覆盖；断点续传只作用于临时文件。
    """
    import requests

    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = save_path.with_name(save_path.name + ".part")
    if chunk_size <= 0 or max_retries < 0:
        raise ValueError("chunk_size 必须为正数，max_retries 不能为负数")

    with _target_lock(save_path):
        if overwrite:
            # 保留旧的完整文件，只有新文件完成后 os.replace 才会替换它。
            part_path.unlink(missing_ok=True)

        attempt = 0
        last_error: Optional[Exception] = None
        while attempt <= max_retries:
            if cancel_event is not None and cancel_event.is_set():
                raise DownloadError(f"下载已取消：{url}")
            downloaded = part_path.stat().st_size if part_path.exists() else 0
            req_headers = dict(headers or {})
            if downloaded:
                req_headers["Range"] = f"bytes={downloaded}-"
            expected_total: Optional[int] = None
            restart_without_counting = False
            response = None
            try:
                logger.debug("[download_stream] 访问 URL：%s", url)
                response = requests.get(
                    url,
                    headers=req_headers,
                    stream=True,
                    timeout=(10, 60),
                )
                response.raise_for_status()
                status_code = getattr(response, "status_code", 200)
                content_range = _parse_content_range(
                    getattr(response, "headers", {}).get("Content-Range")
                )
                if downloaded:
                    # 续传必须得到与本地偏移一致的 206；否则丢弃 .part 后
                    # 立即从零开始，不能把完整响应追加到半截文件后。
                    if status_code == 200:
                        logger.warning(
                            "[download_stream] 服务器忽略 Range，丢弃 .part 并使用完整响应：%s",
                            url,
                        )
                        part_path.unlink(missing_ok=True)
                        downloaded = 0
                    elif status_code != 206 or (content_range is not None and content_range[0] != downloaded):
                        logger.warning(
                            "[download_stream] 服务器未按要求续传（status=%s, range=%s），从头下载：%s",
                            status_code, content_range, url,
                        )
                        part_path.unlink(missing_ok=True)
                        restart_without_counting = True
                    else:
                        expected_total = content_range[2] if content_range is not None else None
                elif content_range is not None:
                    expected_total = content_range[2]

                if not restart_without_counting:
                    headers_map = getattr(response, "headers", {})
                    raw_length = headers_map.get("Content-Length")
                    content_length = None
                    if raw_length not in (None, ""):
                        content_length = int(raw_length)
                        if content_length < 0:
                            raise ValueError("Content-Length 不能为负数")
                    if expected_total is None and content_length is not None:
                        expected_total = downloaded + content_length
                    if content_range is not None and content_length is not None:
                        range_length = content_range[1] - content_range[0] + 1
                        if content_length != range_length:
                            raise IOError("Content-Length 与 Content-Range 不一致")

                    with part_path.open("ab" if downloaded else "wb") as output:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if cancel_event is not None and cancel_event.is_set():
                                raise DownloadError(f"下载已取消：{url}")
                            if not chunk:
                                continue
                            output.write(chunk)
                            downloaded += len(chunk)
                            if progress_cb is not None:
                                progress_cb(downloaded, expected_total)
                    if expected_total is not None and downloaded != expected_total:
                        raise IOError(f"下载不完整：{downloaded}/{expected_total} bytes")
                    if downloaded <= 0:
                        raise IOError("下载响应为空")
            except DownloadError:
                raise
            except (requests.RequestException, OSError, ValueError, TypeError) as exc:
                last_error = exc
                logger.warning(
                    "[download_stream] 第%d次下载%s失败（.part 已下载%d字节）：%s",
                    attempt + 1, url, downloaded, exc,
                )
                attempt += 1
                if attempt > max_retries:
                    break
                time.sleep(min(0.25 * (2 ** (attempt - 1)), 2.0))
                continue
            finally:
                if response is not None:
                    _close_response(response)

            if restart_without_counting:
                continue
            os.replace(part_path, save_path)
            return downloaded

        raise DownloadError(f"下载失败：{url}，原因：{last_error}") from last_error



def merge_video_audio(
    video_path: Path,
    audio_path: Path,
    save_path: Path,
    *,
    progress_cb: Optional[ProgressCallback] = None,
    cancel_event: Optional[threading.Event] = None,
) -> None:
    """使用 ffmpeg 原子生成最终文件，支持取消和 10 分钟硬超时。"""
    ffmpeg = _resolve_ffmpeg()
    if ffmpeg is None:
        raise FFmpegNotFoundError(
            "未检测到 ffmpeg，且未安装 imageio-ffmpeg 库，无法进行音视频合成。"
            "请安装 ffmpeg 并加入系统 PATH，或执行 `pip install imageio-ffmpeg` 使用内置 ffmpeg。"
        )

    video_path = Path(video_path)
    audio_path = Path(audio_path)
    save_path = Path(save_path)
    if not video_path.is_file():
        raise DownloadError(f"视频流文件不存在：{video_path}")
    if not audio_path.is_file():
        raise DownloadError(f"音频流文件不存在：{audio_path}")
    save_path.parent.mkdir(parents=True, exist_ok=True)
    # ffmpeg 依据输出文件扩展名选择封装格式。不能使用 ``video.mp4.part``：
    # 它会把 ``.part`` 当作未知格式并以 EINVAL（Windows 上显示为 4294967274）失败。
    # 将临时标记置于扩展名前，既保留原子替换语义，又让 ffmpeg 正确识别 mp4。
    temp_output = save_path.with_name(f"{save_path.stem}.part{save_path.suffix}")
    temp_output.unlink(missing_ok=True)
    cmd = [ffmpeg, "-y", "-i", str(video_path), "-i", str(audio_path), "-c", "copy", str(temp_output)]
    logger.debug("[merge_video_audio] 合成命令：%s", " ".join(cmd))
    if progress_cb:
        progress_cb(0, None)

    process = None
    try:
        # stdout/stderr 重定向到 DEVNULL，避免 ffmpeg 大量日志填满 PIPE 导致死锁。
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 600
        while True:
            returncode = process.poll()
            if returncode is not None:
                break
            if cancel_event is not None and cancel_event.is_set():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise DownloadError("音视频合成已取消")
            if time.monotonic() >= deadline:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise DownloadError("音视频合成超时（>600s）")
            time.sleep(0.1)

        if returncode != 0:
            raise DownloadError(f"音视频合成失败，返回码 {returncode}")
        if not temp_output.is_file() or temp_output.stat().st_size <= 0:
            raise DownloadError("ffmpeg 未生成有效输出文件")
        os.replace(temp_output, save_path)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        temp_output.unlink(missing_ok=True)
    if progress_cb:
        progress_cb(1, 1)
