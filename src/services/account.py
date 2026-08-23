"""
账号服务：多账号映射表（accounts.json）与当前账号切换。

取代「单一全局 cookie」模型：每个账号一条映射记录 {mid, user_name, cookie_path}，
mid 唯一；cookie_path 显式存储（默认落在全局 cookie 目录下的 <mid>/qr_login.txt）。
切换当前账号 = 把该账号 cookie 路径设为全局生效路径（`path.get_cookie_path()`）。

[使用方法]
    manager = AccountManager()
    manager.switch(12345)                       # 切换账号（写表 + 生效 + 清缓存）
    manager.handle_login(set_cookie)            # 扫码登录成功后的接入
    manager.remove_current()                    # 退出登录：删文件 + 删条目 + 切下一个
"""

import json
import logging
import os
import shutil
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from src.config.cookie import BiliCookies
from src.config.path import ACCOUNTS_FILE, get_cookie_dir, set_cookie_path
from src.models.account_model import Account

logger = logging.getLogger(__name__)

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _thread_lock(path: Path) -> threading.RLock:
    key = str(path.expanduser().resolve()).casefold()
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _file_lock(path: Path):
    """跨进程锁：Windows 用 msvcrt，POSIX 用 flock。"""
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def atomic_write_text(path: Path, text: str, mode: int = 0o600) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
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


class AccountManager:
    """多账号映射表的读写与切换。"""

    def __init__(self, accounts_file: Optional[Path] = None):
        self.accounts_file = Path(accounts_file) if accounts_file else ACCOUNTS_FILE
        self.accounts: list[Account] = []
        self.current_mid: Optional[int] = None
        self.default_mid: Optional[int] = None  # 启动时默认使用的账号（设为默认）
        self._loaded_current_mid: Optional[int] = None
        self._loaded_default_mid: Optional[int] = None
        self._load()

    # ---- 持久化 ----

    def _load(self) -> None:
        self.accounts = []
        self.current_mid = None
        self.default_mid = None
        self._loaded_current_mid = None
        self._loaded_default_mid = None
        if not self.accounts_file.exists():
            return
        try:
            data = json.loads(self.accounts_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("[AccountManager] 账号表损坏，回退为空表：%s", self.accounts_file)
            return
        if not isinstance(data, dict):
            logger.warning("[AccountManager] 账号表顶层必须是对象：%s", self.accounts_file)
            return
        raw_accounts = data.get("accounts")
        if raw_accounts is None:
            raw_accounts = []
        if not isinstance(raw_accounts, list):
            logger.warning("[AccountManager] accounts 必须是列表：%s", self.accounts_file)
            raw_accounts = []
        for raw in raw_accounts:
            if not isinstance(raw, dict):
                continue
            try:
                mid = int(raw.get("mid"))
                cookie_path = raw.get("cookie_path")
                if mid <= 0 or not isinstance(cookie_path, str) or not cookie_path.strip():
                    continue
                self.accounts.append(Account(
                    mid=mid,
                    user_name=str(raw.get("user_name", "")),
                    cookie_path=Path(cookie_path).expanduser().resolve(),
                ))
            except (TypeError, ValueError, OSError):
                logger.warning("[AccountManager] 跳过无效账号记录：%r", raw)

        for attr in ("current_mid", "default_mid"):
            raw_value = data.get(attr)
            try:
                value = int(raw_value) if raw_value is not None else None
            except (TypeError, ValueError):
                value = None
            if value is not None and value <= 0:
                value = None
            setattr(self, attr, value)
            if value is not None and self.get(value) is None:
                setattr(self, attr, None)
        self._loaded_current_mid = self.current_mid
        self._loaded_default_mid = self.default_mid

    def reload(self) -> None:
        """重新从磁盘读取映射表（账号列表可能被其他实例/登录流程修改）。"""
        self._load()

    def save(self) -> None:
        """在跨进程锁内以 fsync + replace 原子写入账号表。"""
        local_accounts = {
            a.mid: {"mid": a.mid, "user_name": a.user_name, "cookie_path": str(a.cookie_path)}
            for a in self.accounts
        }
        self.accounts_file.parent.mkdir(parents=True, exist_ok=True)
        lock = _thread_lock(self.accounts_file)
        with lock, _file_lock(self.accounts_file):
            # 在锁内读取并合并其他进程刚提交的账号，避免两个实例同时登录时
            # 后写入者把先写入者整表覆盖。相同 mid 以当前实例的最新值为准。
            disk_accounts = {}
            existing_data = {}
            if self.accounts_file.exists():
                try:
                    raw = json.loads(self.accounts_file.read_text(encoding="utf-8"))
                    existing_data = raw if isinstance(raw, dict) else {}
                    for item in existing_data.get("accounts", []):
                        if isinstance(item, dict):
                            try:
                                mid = int(item.get("mid"))
                            except (TypeError, ValueError):
                                continue
                            if mid > 0:
                                disk_accounts[mid] = item
                except (OSError, json.JSONDecodeError):
                    logger.warning("[AccountManager] 保存时无法读取旧账号表，将以当前实例内容覆盖：%s", self.accounts_file)
            merged_accounts = {**disk_accounts, **local_accounts}
            current_mid = self.current_mid
            if self.current_mid == self._loaded_current_mid:
                current_mid = existing_data.get("current_mid")
            default_mid = self.default_mid
            if self.default_mid == self._loaded_default_mid:
                default_mid = existing_data.get("default_mid")
            data = {
                "current_mid": current_mid,
                "default_mid": default_mid,
                "accounts": list(merged_accounts.values()),
            }
            atomic_write_text(
                self.accounts_file,
                json.dumps(data, ensure_ascii=False, indent=2),
                mode=0o600,
            )
            self._loaded_current_mid = self.current_mid
            self._loaded_default_mid = self.default_mid

    # ---- 查询 ----

    def list_accounts(self) -> list[Account]:
        return list(self.accounts)

    def get(self, mid: int) -> Optional[Account]:
        for a in self.accounts:
            if a.mid == mid:
                return a
        return None

    def get_current(self) -> Optional[Account]:
        if self.current_mid is None:
            return None
        return self.get(self.current_mid)

    # ---- 变更 ----

    def upsert(self, mid: int, user_name: str, cookie_path) -> Account:
        """新增或更新账号（mid 唯一）。"""
        cookie_path = Path(cookie_path)
        existing = self.get(mid)
        if existing is not None:
            existing.user_name = user_name
            existing.cookie_path = cookie_path
            account = existing
        else:
            account = Account(mid=mid, user_name=user_name, cookie_path=cookie_path)
            self.accounts.append(account)
        self.save()
        return account

    def switch(self, mid: Optional[int]) -> Optional[Account]:
        """切换当前账号并全局生效；None 表示无账号（回落默认 cookie 路径）。"""
        if mid is not None and self.get(mid) is not None:
            self.current_mid = mid
        else:
            self.current_mid = None
        self.save()
        self._apply_current()
        return self.get_current()

    def set_default(self, mid: int) -> Optional[Account]:
        """设为启动默认账号，并立即切换生效。"""
        account = self.get(mid)
        if account is None:
            return None
        self.default_mid = mid
        self.switch(mid)  # switch 内部会 save（连同 default_mid 一起持久化）
        return account

    def remove(self, mid: int, *, delete_file: bool = True) -> Optional[Account]:
        """删除账号（可选删 cookie 文件）。若删除的是当前账号，自动切到剩余第一个。"""
        account = self.get(mid)
        if account is None:
            return None
        self.accounts.remove(account)
        if self.current_mid == mid:
            self.current_mid = self.accounts[0].mid if self.accounts else None
        if delete_file:
            try:
                account.cookie_path.unlink(missing_ok=True)
            except OSError as e:
                logger.warning("[AccountManager] 删除 cookie 文件失败：%s", e)
        self.save()
        self._apply_current()
        return account

    def remove_current(self) -> Optional[Account]:
        """退出登录：删除当前账号（含 cookie 文件）并切换。"""
        current = self.get_current()
        if current is None:
            return None
        return self.remove(current.mid)

    def relocate(self, old_dir, new_dir) -> None:
        """把 cookie 位于 `old_dir` 之下的账号 cookie 按相对结构迁到 `new_dir`，并更新映射。

        仅在目标不存在时移动（不覆盖）；不在旧目录下的自定义路径不动。
        """
        old_dir = Path(old_dir)
        new_dir = Path(new_dir)
        if new_dir == old_dir:
            return
        changed = False
        for account in self.accounts:
            try:
                rel = account.cookie_path.relative_to(old_dir)
            except ValueError:
                continue  # 自定义路径，不在旧目录下
            dst = new_dir / rel
            if account.cookie_path.exists() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(account.cookie_path), str(dst))
            account.cookie_path = dst
            changed = True
        if changed:
            self.save()

    def apply_startup(self) -> None:
        """启动装配：优先应用「默认账号」，其次当前账号；无则回落默认路径。

        只改内存状态，不写盘（避免每次启动都重写账号表）。
        """
        mid = None
        if self.default_mid is not None and self.get(self.default_mid) is not None:
            mid = self.default_mid
        elif self.current_mid is not None and self.get(self.current_mid) is not None:
            mid = self.current_mid
        self.current_mid = mid
        self._apply_current()

    def _apply_current(self) -> None:
        current = self.get_current()
        set_cookie_path(current.cookie_path if current is not None else None)
        BiliCookies.clear_cache()

    # ---- 登录接入 ----

    def default_cookie_path(self, mid: int) -> Path:
        """新账号 cookie 的默认落点：<全局 cookie 目录>/<mid>/qr_login.txt。"""
        return get_cookie_dir() / str(mid) / "qr_login.txt"

    def handle_login(self, set_cookie: str) -> Optional[Account]:
        """扫码登录成功后的接入：解析 mid → 写 cookie 文件 → 建/更新账号 → 切换。

        :param set_cookie: 登录成功响应头里的 set-cookie 原始字符串
        :return: 当前账号；失败时返回 None
        """
        try:
            cookies = BiliCookies(cookie=set_cookie)
            mid = cookies.mid if cookies.mid is not None else self._resolve_mid_online(set_cookie)
            if mid is None or int(mid) <= 0:
                raise ValueError("登录凭证中无法解析有效 UID")
            mid = int(mid)
            save_path = self.default_cookie_path(mid)
            atomic_write_text(save_path, set_cookie.strip(), mode=0o600)
            # 登录响应先落盘并登记账号，再切换全局 cookie 路径；
            # 只有 switch 完成后，下面的昵称查询才会读取新账号凭证。
            account = self.upsert(mid, "", save_path)
            self.switch(mid)  # 先切换，下面的昵称查询读的才是新账号 cookie
            account.user_name = self._resolve_uname() or f"账号{mid}"
            self.save()
            return account
        except Exception as e:
            logger.exception("[AccountManager] 登录接入失败：%s", e)
            return None

    @staticmethod
    def _resolve_mid_online(set_cookie: str) -> Optional[int]:
        """set-cookie 无 DedeUserID 时，临时构造会话查询 uid。"""
        try:
            import tempfile

            from src.api.session import BiliSession
            from src.services.login import LoginService

            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "cookie.txt"
                atomic_write_text(p, set_cookie.strip(), mode=0o600)
                session = BiliSession(cookie_path=str(p))
                try:
                    return LoginService(session).get_login_state().mid
                finally:
                    session.close()
        except Exception as e:
            logger.warning("[AccountManager] 在线解析 uid 失败：%s", e)
            return None

    @staticmethod
    def _resolve_uname() -> str:
        """查询当前账号昵称（读的是当前生效 cookie，需在 switch 之后调用）。"""
        try:
            from src.services.login import LoginService

            user = LoginService().get_login_state()
            return user.uname or "" if user.is_login else ""
        except Exception as e:
            logger.warning("[AccountManager] 获取昵称失败：%s", e)
            return ""
