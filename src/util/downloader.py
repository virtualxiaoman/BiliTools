"""
下载工具：DASH 流的下载与 ffmpeg 音视频合成。

- `download_stream`     下载单个媒体流到本地文件（流式写入，支持进度回调）；
- `merge_video_audio`   用 ffmpeg 合成音视频（subprocess 列表参数，避免 shell 注入）；
- `ffmpeg_available`    ffmpeg 可用性探测（带缓存）。

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

# ffmpeg 可用性探测结果缓存（避免每次调用都执行 which）
_ffmpeg_checked: bool = False
_ffmpeg_ok: bool = False


def ffmpeg_available() -> bool:
    """检查系统是否安装了 ffmpeg（结果缓存，避免每次探测）。"""
    global _ffmpeg_checked, _ffmpeg_ok
    if not _ffmpeg_checked:
        _ffmpeg_ok = shutil.which("ffmpeg") is not None
        _ffmpeg_checked = True
    return _ffmpeg_ok


def download_stream(
    url: str,
    save_path: Path,
    headers: Optional[dict] = None,
    *,
    progress_cb: Optional[ProgressCallback] = None,
    chunk_size: int = 1024 * 256,
) -> int:
    """
    下载单个媒体流（如 DASH 视频/音频流）到本地文件。

    [注意]
    下载响应必须带正确的 Referer（B 站要求 referer 为 https://www.bilibili.com）。

    :param url: 媒体直链
    :param save_path: 保存路径（父目录需已存在）
    :param headers: 请求头（用于补充 Cookie/Referer）
    :param progress_cb: 进度回调 (downloaded, total)
    :param chunk_size: 分块大小（字节）
    :return: 下载的文件大小（字节）
    :raises DownloadError: 请求或写入失败
    """
    import requests

    save_path = Path(save_path)
    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=30)
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0)) or None
        downloaded = 0
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)
        return downloaded
    except requests.RequestException as e:
        raise DownloadError(f"下载失败：{url}，原因：{e}") from e
    except OSError as e:
        raise DownloadError(f"写入文件失败：{save_path}，原因：{e}") from e


def merge_video_audio(
    video_path: Path,
    audio_path: Path,
    save_path: Path,
    *,
    progress_cb: Optional[ProgressCallback] = None,
) -> None:
    """
    使用 ffmpeg 将视频流与音频流合成为单文件。

    [使用方法]:
        merge_video_audio(Path("video.m4s"), Path("audio.m4a"), Path("output.mp4"))
    :param video_path: 视频流文件完整路径
    :param audio_path: 音频流文件完整路径
    :param save_path: 合成后的文件保存路径
    :param progress_cb: 进度回调（ffmpeg 阶段仅作状态提示，无精确字节数）
    :raises FFmpegNotFoundError: 系统未安装 ffmpeg
    :raises DownloadError: 合成失败（ffmpeg 返回非零）
    """
    if not ffmpeg_available():
        raise FFmpegNotFoundError("未检测到 ffmpeg，无法进行音视频合成。请先安装 ffmpeg 并加入系统 PATH。")

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
    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path), "-c", "copy", str(save_path)]
    logger.info("[merge_video_audio] ffmpeg 命令：%s", " ".join(cmd))
    if progress_cb:
        progress_cb(0, None)
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise DownloadError("ffmpeg 合成超时（>600s），请检查视频是否过大。")
    if result.returncode != 0:
        err_tail = result.stderr.decode("utf-8", errors="replace")[-500:] if result.stderr else ""
        raise DownloadError(f"ffmpeg 合成失败，返回码 {result.returncode}：{err_tail}")
    if progress_cb:
        progress_cb(1, 1)
