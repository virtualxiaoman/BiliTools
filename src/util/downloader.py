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
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from src.api.errors import DownloadError, FFmpegNotFoundError

logger = logging.getLogger(__name__)

# 进度回调签名：已下载字节数, 总字节数（总字节数可能为 None/0）
ProgressCallback = Callable[[int, Optional[int]], None]

# 合成后端探测结果缓存（避免每次调用都执行 which / 导入 imageio）
_ffmpeg_checked: bool = False
_ffmpeg_path: Optional[str] = None


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
) -> int:
    """
    下载单个媒体流（如 DASH 视频/音频流）到本地文件。

    [注意]
    下载响应必须带正确的 Referer（B 站要求 referer 为 https://www.bilibili.com）。

    网络中断（连接断开/读取不完整）时会自动**断点续传**：用 Range 头从已下载位置
    继续，最多重试 `max_retries` 次。续传时会校验服务器是否返回 206（Partial
    Content）——若服务器忽略 Range 返回 200 全量内容，会丢弃半截文件从头下载，
    避免把全量内容追加到半截文件后造成文件损坏。

    :param url: 媒体直链
    :param save_path: 保存路径（父目录需已存在）
    :param headers: 请求头（用于补充 Cookie/Referer）
    :param progress_cb: 进度回调 (downloaded, total)
    :param chunk_size: 分块大小（字节）
    :param max_retries: 断点续传的最大重试次数
    :return: 下载的文件大小（字节）
    :raises DownloadError: 下载失败（重试后仍失败）
    """
    import requests

    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    total: Optional[int] = None
    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        downloaded = save_path.stat().st_size if save_path.exists() else 0
        req_headers = dict(headers) if headers else {}
        resuming = downloaded > 0
        if resuming:
            # 断点续传：从已下载位置继续
            req_headers["Range"] = f"bytes={downloaded}-"
        try:
            resp = requests.get(url, headers=req_headers, stream=True, timeout=30)
            resp.raise_for_status()
            if resuming and resp.status_code != 206:
                # 服务器忽略/不支持 Range（返回 200 全量内容等）：
                # 丢弃半截文件从头下载，避免把全量内容追加到半截文件后损坏。
                logger.warning(
                    "[download_stream] 断点续传未获 206（status=%s），丢弃半截文件从头下载：%s",
                    resp.status_code, url,
                )
                save_path.unlink(missing_ok=True)
                downloaded = 0
                resuming = False
            if total is None:
                total = int(resp.headers.get("Content-Length", 0)) or None
                if resuming and total is not None:
                    # 响应的是剩余部分，补上已下载的偏移
                    total += downloaded
            with open(save_path, "ab" if resuming else "wb") as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb:
                            progress_cb(downloaded, total)
            return downloaded
        except (requests.RequestException, OSError) as e:
            last_error = e
            logger.warning(
                "[download_stream]第%d次下载%s失败（已下载%d字节）：%s",
                attempt + 1, url, downloaded, e,
            )
            if attempt >= max_retries:
                break
            # 继续循环：从 save_path 当前大小续传
    raise DownloadError(f"下载失败：{url}，原因：{last_error}") from last_error


def merge_video_audio(
    video_path: Path,
    audio_path: Path,
    save_path: Path,
    *,
    progress_cb: Optional[ProgressCallback] = None,
) -> None:
    """
    使用 ffmpeg 将视频流与音频流合成为单文件。

    合成后端按优先级自动选择：系统 PATH 中的 ffmpeg → imageio-ffmpeg 库内置的
    静态 ffmpeg。无系统 ffmpeg 时无需手动安装，`pip install imageio-ffmpeg` 即可。

    [使用方法]:
        merge_video_audio(Path("video.m4s"), Path("audio.m4a"), Path("output.mp4"))
    :param video_path: 视频流文件完整路径
    :param audio_path: 音频流文件完整路径
    :param save_path: 合成后的文件保存路径
    :param progress_cb: 进度回调（合成阶段仅作状态提示，无精确字节数）
    :raises FFmpegNotFoundError: 未检测到 ffmpeg 且未安装 imageio-ffmpeg
    :raises DownloadError: 合成失败（后端返回非零）
    """
    ffmpeg = _resolve_ffmpeg()
    if ffmpeg is None:
        raise FFmpegNotFoundError(
            "未检测到 ffmpeg，且未安装 imageio-ffmpeg 库，无法进行音视频合成。"
            "请安装 ffmpeg 并加入系统 PATH，或执行 `pip install imageio-ffmpeg` 使用内置 ffmpeg。"
        )

    video_path = Path(video_path)
    audio_path = Path(audio_path)
    save_path = Path(save_path)
    if not video_path.exists():
        raise DownloadError(f"视频流文件不存在：{video_path}")
    if not audio_path.exists():
        raise DownloadError(f"音频流文件不存在：{audio_path}")

    save_path.parent.mkdir(parents=True, exist_ok=True)
    # 列表参数传入，避免 shell 拼接（路径含空格/引号也不会出错）。
    # -y 覆盖已存在的目标文件，避免 ffmpeg 交互式询问导致挂起。
    cmd = [ffmpeg, "-y", "-i", str(video_path), "-i", str(audio_path), "-c", "copy", str(save_path)]
    logger.debug("[merge_video_audio] 合成命令：%s", " ".join(cmd))
    if progress_cb:
        progress_cb(0, None)
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise DownloadError("音视频合成超时（>600s），请检查视频是否过大。")
    if result.returncode != 0:
        err_tail = result.stderr.decode("utf-8", errors="replace")[-500:] if result.stderr else ""
        raise DownloadError(f"音视频合成失败，返回码 {result.returncode}：{err_tail}")
    if progress_cb:
        progress_cb(1, 1)
