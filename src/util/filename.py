"""
文件名清洗与统一命名规则。

命名规则：`[标题](BV号).扩展名`，例如 `测试标题(BV1ov42117yC).mp4`。
清洗逻辑原散落在前端（frontend/download_ui.py 的正则），现下沉后端统一实现。
"""

import re
from pathlib import Path

# Windows 文件名非法字符集合：反斜杠 / 冒号 / 星号 / 问号 / 双引号 / 尖括号 / 竖线
_INVALID_CHARS_RE = re.compile(r'[\\/:*?"<>|]')
# 控制字符（\x00-\x1f 等）与部分不可见字符
_CONTROL_CHARS_RE = re.compile(r'[\x00-\x1f\x7f]')
# 文件名末尾的点或空格（Windows 不允许）
_TRAILING_DOT_SPACE_RE = re.compile(r'[. ]+$')
# 连续空白合并（前端旧逻辑会去除所有空白；这里仅合并为单个空格，更可读）
_WHITESPACE_RE = re.compile(r'\s+')

# Windows 保留设备名（不区分大小写）
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# 文件名长度上限（含扩展名），超出则截断标题部分
_MAX_FILENAME_LEN = 255


def sanitize_filename(name: str, *, keep_whitespace: bool = True) -> str:
    """
    清洗文件名字符串，使其可以安全地用作 Windows/主流系统文件名。

    - 删除非法字符（反斜杠、斜杠、冒号、星号、问号、双引号、尖括号、竖线）与控制字符；
    - 去掉首尾空白；可选将内部连续空白合并为单个空格；
    - 去除末尾的点/空格；处理 Windows 保留设备名；
    - 总长度超过上限时截断。

    :param name: 原始名称（通常是视频标题）
    :param keep_whitespace: 为 True 时合并内部连续空白为单个空格，为 False 时删除所有空白
    :return: 清洗后的文件名（不含扩展名）
    """
    name = _INVALID_CHARS_RE.sub("", name)
    name = _CONTROL_CHARS_RE.sub("", name)
    if keep_whitespace:
        name = _WHITESPACE_RE.sub(" ", name).strip()
    else:
        name = re.sub(r"\s+", "", name)
    name = _TRAILING_DOT_SPACE_RE.sub("", name)
    if not name:
        name = "untitled"
    if name.upper() in _WINDOWS_RESERVED_NAMES:
        name = "_" + name
    return name[: _MAX_FILENAME_LEN]


def build_download_filename(title: str, bvid: str, ext: str = "mp4") -> str:
    """
    按统一规则生成下载文件名：`[清洗后的标题](BV号).扩展名`。

    [使用方法]:
        build_download_filename("测试标题", "BV1ov42117yC")  # "测试标题(BV1ov42117yC).mp4"
    :param title: 视频标题（内部会做文件名清洗）
    :param bvid: BV号
    :param ext: 扩展名（不含点，如 mp4/flv/m4s），由实际媒体流格式决定
    :return: 完整文件名
    """
    safe_title = sanitize_filename(title)
    return f"{safe_title}({bvid}).{ext.lstrip('.')}"


def resolve_save_path(directory, filename: str) -> Path:
    """拼接保存目录与文件名，并确保目录存在（幂等）。"""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / filename
