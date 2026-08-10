"""
Cookie 模型：读取、解析、缓存。

取代旧 `src/config.py` 中的 `BiliCookies`：
- 解析逻辑统一于此（SESSDATA / bili_jct 提取），不再散落两处；
- 进程内缓存：同一路径的 cookie 只读一次、解析一次，重新登录后调用 `refresh()` 更新；
- 不再使用 `exit(1)` 杀进程，改为抛出异常由上层决定处理方式。

[注意]
cookie 的路径全局统一管理，默认读取 `DEFAULT_COOKIE_PATH`，
除非显式传入自定义路径，否则不需要也不应到处传 cookie 路径。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Optional

from src.config.constants import UserAgent
from src.config.path import DEFAULT_COOKIE_PATH


@dataclass
class BiliCookies:
    """
    B 站 Cookie：保存原始字符串，并提供解析后的字段。

    属性：
        cookie: 原始 cookie 字符串（分号分隔的键值对）
        SESSDATA: 登录凭证，鉴权核心字段
        bili_jct: CSRF Token，写操作（评论/私信/投币等）必带
    """

    cookie: str = field(default="")
    SESSDATA: Optional[str] = field(default=None, init=False)
    bili_jct: Optional[str] = field(default=None, init=False)

    # ---- 进程内缓存：同一路径只解析一次 ----
    _cache: ClassVar[dict] = {}

    def __post_init__(self) -> None:
        self._parse()

    def _parse(self) -> None:
        """从原始 cookie 中提取 SESSDATA 与 bili_jct（解析失败不抛异常，仅置为 None）。"""
        self.SESSDATA = self._get_field("SESSDATA")
        self.bili_jct = self._get_field("bili_jct")

    def _get_field(self, key: str) -> Optional[str]:
        for part in self.cookie.split(";"):
            part = part.strip()
            if part.startswith(f"{key}="):
                return part[len(key) + 1:]
        return None

    @property
    def has_valid_session(self) -> bool:
        """是否具备有效登录凭证：SESSDATA 存在即视为已登录。"""
        return bool(self.SESSDATA)

    # ---- 读取与缓存 ----

    @classmethod
    def from_file(cls, path: Optional[Path] = None):
        """从文件读取 cookie 并解析。同一路径的结果会在进程内缓存。

        :param path: cookie 文件路径。默认为 None，使用全局统一的 DEFAULT_COOKIE_PATH
        :return: BiliCookies 实例
        :raises FileNotFoundError: cookie 文件不存在
        """
        if path is None:
            path = DEFAULT_COOKIE_PATH
        path = Path(path)
        if str(path) not in cls._cache:
            cls._cache[str(path)] = cls._read_file(path)
        return cls._cache[str(path)]

    @classmethod
    def _read_file(cls, path: Path) -> "BiliCookies":
        if not path.exists():
            raise FileNotFoundError(
                f"Cookie 文件未找到，请确保文件存在于路径: {path.resolve()}"
            )
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # 兼容个别以 GBK/GB2312 保存的 cookie 文件
            raw = path.read_text(encoding="gbk")
        return cls(cookie=raw.strip())

    @classmethod
    def refresh(cls, path: Optional[Path] = None):
        """强制重新读取指定路径的 cookie（覆盖缓存），供重新登录后调用。

        :param path: cookie 文件路径。默认为 None，使用全局统一的 DEFAULT_COOKIE_PATH
        """
        if path is None:
            path = DEFAULT_COOKIE_PATH
        cls._cache.pop(str(Path(path)), None)
        return cls.from_file(path)

    # ---- 请求头 ----

    def to_headers(self, referer: str = "https://www.bilibili.com/", user_agent: Optional[str] = None) -> dict:
        """生成带 Cookie 的请求头。

        :param referer: 引用来源，默认 B 站主站
        :param user_agent: User-Agent，默认为 None，使用 UserAgent().pcChrome
        """
        if user_agent is None:
            user_agent = UserAgent().pcChrome
        return {
            "User-Agent": user_agent,
            "Cookie": self.cookie,
            "Referer": referer,
        }

    def __repr__(self) -> str:
        # 避免在日志/调试中泄露完整 cookie
        return f"BiliCookies(SESSDATA={'<set>' if self.SESSDATA else None})"
