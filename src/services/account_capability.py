"""账号能力探测：大会员状态，以及一次下载任务内共享的权限结论缓存。

GUI 点击下载时用 `list_account_capabilities()` 判断各账号是否具备大会员，
下载线程复用同一份探测结果（进程内短缓存），避免重复请求 nav。
`AccountPermissionCache` 挂在 `VideoService` 上，供多线程/换号共享
“哪些账号能播放充电视频、视频实际最高清晰度”的结论。
"""

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.api.session import BiliSession
from src.config.cookie import BiliCookies
from src.services.login import LoginService

logger = logging.getLogger(__name__)

_CACHE_TTL = 60.0
_caps_lock = threading.Lock()
_caps_cache: Optional[tuple[float, list["AccountCapability"]]] = None


def _normalize_path(path) -> str:
    try:
        return str(Path(path).expanduser().resolve()).casefold()
    except OSError:
        return str(path).casefold()


def same_account(path_a, path_b) -> bool:
    """两个 cookie 路径是否指向同一个账号（Windows 路径大小写不敏感）。"""
    if not path_a or not path_b:
        return False
    return _normalize_path(path_a) == _normalize_path(path_b)


def session_mid(session) -> Optional[int]:
    """会话 cookie 里的账号 mid（DedeUserID；读取不到时为 None）。"""
    mid = getattr(getattr(session, "cookie", None), "mid", None)
    try:
        return int(mid) if mid else None
    except (TypeError, ValueError):
        return None


def capability_matches_session(cap: "AccountCapability", session) -> bool:
    """能力条目是否对应某个会话：优先按 mid 判定（当前账号 cookie 可能是共享路径）。"""
    if same_account(cap.cookie_path, getattr(session, "cookie_path", "")):
        return True
    mid = session_mid(session)
    return bool(mid) and cap.mid == mid


@dataclass(frozen=True)
class AccountCapability:
    """单个账号的能力快照。

    :param is_vip: None 表示探测失败（按“不忽略”处理，避免误伤下载）
    """

    cookie_path: str
    uname: str = ""
    mid: Optional[int] = None
    is_vip: Optional[bool] = None

    @property
    def key(self) -> str:
        return _normalize_path(self.cookie_path)


def probe_session_capability(session: BiliSession, fallback_name: str = "") -> AccountCapability:
    """探测一个已建会话的登录/大会员状态（一次 nav 请求）。

    网络失败时 `is_vip=None`；未登录时 `is_vip=False`。
    """
    path = str(getattr(session, "cookie_path", "") or "")
    try:
        user = LoginService(session).get_login_state()
    except Exception:
        logger.warning("[AccountCapability] 账号探测失败：%s", path, exc_info=True)
        return AccountCapability(cookie_path=path, uname=fallback_name or "未知账号")
    return AccountCapability(
        cookie_path=path,
        uname=user.uname or fallback_name or "未知账号",
        mid=user.mid,
        is_vip=user.is_vip if user.is_login else False,
    )


def list_account_capabilities(force: bool = False) -> list[AccountCapability]:
    """枚举账号映射表中的有效账号并探测能力（进程内缓存 60 秒）。"""
    global _caps_cache
    if not force:
        with _caps_lock:
            if _caps_cache is not None and time.monotonic() - _caps_cache[0] < _CACHE_TTL:
                return list(_caps_cache[1])

    from src.services.account import AccountManager

    caps: list[AccountCapability] = []
    for account in AccountManager().list_accounts():
        try:
            cookies = BiliCookies.from_file(account.cookie_path)
        except OSError:
            continue
        if not cookies.has_valid_session:
            continue
        session = BiliSession(cookie_path=str(account.cookie_path))
        try:
            caps.append(probe_session_capability(session, account.user_name))
        finally:
            session.close()
    with _caps_lock:
        _caps_cache = (time.monotonic(), caps)
    return list(caps)


def capability_for(session, caps: list[AccountCapability]) -> Optional[AccountCapability]:
    """在能力列表中匹配某个会话对应的账号。"""
    for cap in caps:
        if capability_matches_session(cap, session):
            return cap
    return None


def invalidate_capability_cache() -> None:
    global _caps_cache
    with _caps_lock:
        _caps_cache = None


class AccountPermissionCache:
    """一次下载任务内共享的权限结论（跨线程、跨临时会话）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._upower_account: dict[int, str] = {}
        self._max_quality: dict[tuple[str, int], int] = {}

    def remember_upower_account(self, up_mid: int, cookie_path: str) -> None:
        if not up_mid or not cookie_path:
            return
        with self._lock:
            self._upower_account[int(up_mid)] = str(cookie_path)

    def upower_account(self, up_mid: int) -> Optional[str]:
        with self._lock:
            return self._upower_account.get(int(up_mid or 0))

    def remember_max_quality(self, bvid: str, cid: int, quality: int) -> None:
        if not bvid or not cid or not quality:
            return
        with self._lock:
            self._max_quality[(bvid, int(cid))] = int(quality)

    def max_quality(self, bvid: str, cid: int) -> Optional[int]:
        with self._lock:
            return self._max_quality.get((bvid, int(cid or 0)))
