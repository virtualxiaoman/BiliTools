"""输入归一化与登录状态工具（UI 层，不改 src 语义）。

所有下载入口都支持「直接传参数」或「传完整 URL」两种方式，统一归一化为规范 id，
既保证任务去重 key 稳定，也让非法输入在开线程之前就报错。

归一化只做本地解析（正则 / av2bv），不发网络请求；本地解析不出的链接（如 b23.tv
短链）会抛 NeedsUrlResolution，由下载线程（DownloadWorker）通过 follow_redirect
跟随跳转后再解析，避免阻塞界面线程。
"""
import re
from typing import Optional

import requests

from src.config.constants import UserAgent
from src.config.cookie import BiliCookies
from src.config.path import get_cookie_path
from src.util.bvid import av2bv

_BV_RE = re.compile(r"bv[0-9a-zA-Z]{10}", re.IGNORECASE)
# av 号：前缀（^）或非字母数字边界，避免误匹配 query 值里嵌入的 "av123" 之类文本
_AV_RE = re.compile(r"(?:^|[^0-9a-zA-Z])av(\d+)", re.IGNORECASE)
_SPACE_MID_RE = re.compile(r"space\.bilibili\.com/(\d+)")
_FAV_FID_RE = re.compile(r"[?&]fid=(\d+)")
_SEASON_SID_RE = re.compile(r"[?&]sid=(\d+)")
_SEASON_LIST_RE = re.compile(r"space\.bilibili\.com/(\d+)/lists/(\d+)")
_PAGE_RE = re.compile(r"[?&]p=(\d+)")
# 从「标题+URL」文本中提取 URL：以 http(s):// 起，到空白/中文/全角标点为止
_URL_RE = re.compile(
    r"https?://[^\s　-〿一-鿿＀-￯…—]+",
    re.IGNORECASE,
)


def extract_page_from_url(raw: str) -> Optional[int]:
    """从视频链接中提取分P参数 `p=n`；仅当输入为链接时尝试，无 p 参数返回 None。

    [例子] https://www.bilibili.com/video/BV1ws411v7zE?spm_id_from=...&p=2  → 2
    """
    s = raw.strip()
    if "http" not in s.lower():
        return None
    m = _PAGE_RE.search(s)
    return int(m.group(1)) if m else None


def ensure_cookie_file() -> None:
    """确保 cookie 文件存在（全新安装时为空文件，has_valid_session=False 走未登录分支）。

    BiliSession 对缺失文件已降级为匿名会话（不抛异常）；
    此函数仍保证文件存在，供仍直接调用 BiliCookies.from_file 的取 CSRF 等场景使用
    （该函数在文件缺失时仍抛 FileNotFoundError，有测试依赖）。
    """
    path = get_cookie_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")


def has_valid_session() -> bool:
    """本地快速判断是否具备登录凭证（SESSDATA 存在）。不发起网络请求。"""
    try:
        return BiliCookies.from_file().has_valid_session
    except FileNotFoundError:
        return False


class NeedsUrlResolution(Exception):
    """输入是链接但本地解析不出目标 ID，需在下载线程内跟随跳转后再解析。"""

    def __init__(self, url: str):
        super().__init__(url)
        self.url = url


def follow_redirect(url: str, timeout: int = 15) -> str:
    """跟随 HTTP 跳转返回最终 URL（处理 b23.tv 等短链）。仅应在工作线程调用。"""
    r = requests.get(
        url, allow_redirects=True, timeout=timeout,
        headers={"User-Agent": UserAgent().pcChrome},
    )
    r.raise_for_status()
    return r.url


def resolve_input(source: str, raw: str):
    """在下载线程内把原始输入解析为规范值（必要时跟随短链跳转后重试）。

    :param source: "bv" / "fav" / "season" / "up"
    :param raw: 用户原始输入（可能是短链）
    :return: 与各 tab 对应的规范值：BV号 str / fid int / (kind, val, mid) / mid int
    """
    attempts = 0
    while True:
        try:
            if source == "bv":
                return normalize_bvid(raw)
            if source == "fav":
                return normalize_fav(raw)
            if source == "season":
                return normalize_season(raw)
            if source == "up":
                return normalize_mid(raw)
            raise ValueError(f"未知下载来源：{source}")
        except NeedsUrlResolution as e:
            attempts += 1
            if attempts > 1:
                raise ValueError(f"无法从输入解析：{raw}") from e
            try:
                raw = follow_redirect(e.url)
            except requests.RequestException as exc:
                raise ValueError(f"访问链接失败：{exc}") from exc


# ---- 归一化 ----

def normalize_bvid(raw: str) -> str:
    """输入 BV/bv 号、av 号或视频链接 → 返回 BV 号。

    只做本地解析（正则 / av2bv），不发网络请求；输入是链接但本地解析不出 BV 时抛
    NeedsUrlResolution，由下载线程跟随跳转后再解析（见 resolve_input）。
    """
    s = raw.strip()
    if not s:
        raise ValueError("输入为空")
    m = _BV_RE.search(s)
    if m:
        b = m.group(0)
        return b[:2].upper() + b[2:]  # 保留原有大小写，仅修正 bv 前缀
    # av 号：裸输入 "av123" 或链接路径中的 "/video/av123" 都直接本地转换，
    # 不再依赖网络请求去等 bilibili 301 跳转（av 号不存在时页面不跳转，会解析失败）
    m = _AV_RE.search(s)
    if m:
        return av2bv(m.group(1))
    m = _URL_RE.search(s)
    if m:
        # 「标题+URL」等格式：只携带提取出的干净 URL，交给下载线程跟随跳转
        raise NeedsUrlResolution(m.group(0))
    raise ValueError(f"无法从输入解析 BV 号：{raw}")


def normalize_fav(raw: str) -> int:
    """输入 media_id 或收藏夹链接 → 返回 media_id。

    只做本地解析；输入是链接但提取不出 fid 时抛 NeedsUrlResolution，由下载线程跟随跳转。
    """
    s = raw.strip()
    if not s:
        raise ValueError("输入为空")
    if s.isdigit():
        return int(s)
    m = _FAV_FID_RE.search(s)
    if m:
        return int(m.group(1))
    m = _URL_RE.search(s)
    if m:
        raise NeedsUrlResolution(m.group(0))
    raise ValueError(f"无法从输入解析收藏夹 media_id：{raw}")


def normalize_season(raw: str):
    """输入合集参数/链接 → 返回 (kind, value, mid)。

    - BV号/视频链接 → ("bvid", bvid, None)
    - sid 数字 → ("sid", sid, 0)
    - 合集空间链接 `space.bilibili.com/<mid>/lists/<sid>` → ("sid", sid, mid)
      （按路径结构匹配，不依赖 ?type=season）
    - 带 sid 参数的合集链接 → ("sid", sid, mid|0)
    """
    s = raw.strip()
    if not s:
        raise ValueError("输入为空")
    if s.isdigit():
        return ("sid", int(s), 0)
    # 合集空间链接：/mid/lists/sid
    m = _SEASON_LIST_RE.search(s)
    if m:
        return ("sid", int(m.group(2)), int(m.group(1)))
    # 带 sid 参数的合集链接
    m = _SEASON_SID_RE.search(s)
    if m:
        sid = int(m.group(1))
        mm = _SPACE_MID_RE.search(s)
        mid = int(mm.group(1)) if mm else 0
        return ("sid", sid, mid)
    bvid = normalize_bvid(s)
    return ("bvid", bvid, None)


def normalize_mid(raw: str) -> int:
    """输入 mid 或空间链接 → 返回 mid。

    只做本地解析；输入是链接但提取不出 mid 时抛 NeedsUrlResolution，由下载线程跟随跳转。
    """
    s = raw.strip()
    if not s:
        raise ValueError("输入为空")
    if s.isdigit():
        return int(s)
    m = _SPACE_MID_RE.search(s)
    if m:
        return int(m.group(1))
    m = _URL_RE.search(s)
    if m:
        raise NeedsUrlResolution(m.group(0))
    raise ValueError(f"无法从输入解析 UP主 mid：{raw}")
