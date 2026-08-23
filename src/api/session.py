"""
统一请求层：BiliSession。

职责：
- 为所有 B 站 API 请求注入统一的 User-Agent / Referer / Cookie；
- 解析响应 JSON 并统一检查 code 字段（code != 0 抛异常）；
- 支持失败自动重试（替代旧代码里散落各处的 while 重试循环）。

[使用方法]
    session = BiliSession()                       # 使用当前账号 cookie（默认 %APPDATA%/xiaoman/BiliTools）
    data = session.get(VideoUrls.VIEW, params={"bvid": "BV1ov42117yC"})  # 返回 data 字典
"""

import logging
import random
import time
from pathlib import Path
from typing import Optional

import requests

from src.config.constants import MAX_RETRY, REQUEST_TIMEOUT, RETRY_DELAY
from src.config.cookie import BiliCookies
from src.config.path import get_cookie_path
from src.api.errors import raise_for_code

logger = logging.getLogger(__name__)


class BiliSession:
    """B 站 API 的统一请求客户端。"""

    def __init__(
        self,
        cookie_path: Optional[str] = None,
        referer: str = "https://www.bilibili.com/",
        max_retry: int = MAX_RETRY,
        timeout: float = REQUEST_TIMEOUT,
    ):
        """
        :param cookie_path: cookie 文件路径。None 时使用全局生效路径 get_cookie_path()
                            （多账号体系下即当前账号的 cookie）。cookie 读取结果在
                            BiliCookies 内做进程级缓存。
        :param referer: 默认 Referer，可用 session.get/post 的 headers 参数覆盖。
        :param max_retry: 请求失败时的最大重试次数（不含首次）。
        :param timeout: 单次请求超时（秒）。
        """
        self.cookie_path = str(cookie_path) if cookie_path is not None else str(get_cookie_path())
        self.cookie = self._load_cookie(self.cookie_path)
        self.referer = referer
        self.max_retry = max_retry
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.cookie.to_headers(referer=referer))

    @staticmethod
    def _load_cookie(cookie_path: Optional[str]) -> "BiliCookies":
        """读取 cookie；本地无 cookie 文件时以匿名会话（空 cookie）代替，不抛异常。

        免鉴权接口（QR 登录、nav 状态查询、热门榜单等）可直接使用；
        需要登录的接口由服务端返回未登录错误（BiliAuthError）。
        """
        try:
            return BiliCookies.from_file(cookie_path)
        except FileNotFoundError:
            logger.warning("[BiliSession] cookie 文件缺失，以未登录状态请求（路径：%s）",
                           Path(cookie_path).resolve() if cookie_path else get_cookie_path())
            return BiliCookies()

    # ---- 请求入口 ----

    def get(self, url: str, params: Optional[dict] = None, headers: Optional[dict] = None, **kwargs) -> dict:
        """GET 请求，返回业务 data 字段（dict）。"""
        return self._request("GET", url, params=params, headers=headers, **kwargs)

    def post(self, url: str, data: Optional[dict] = None, params: Optional[dict] = None,
             headers: Optional[dict] = None, *, retryable: bool = False, **kwargs) -> dict:
        """POST 请求，默认不重试；只有确认幂等时显式设置 retryable=True。"""
        return self._request("POST", url, data=data, params=params, headers=headers,
                             retryable=retryable, **kwargs)

    def get_raw(
        self,
        url: str,
        headers: Optional[dict] = None,
        *,
        max_bytes: int = 16 * 1024 * 1024,
        **kwargs,
    ) -> bytes:
        """流式读取有限大小的二进制响应。"""
        if max_bytes <= 0:
            raise ValueError("max_bytes 必须为正数")
        if headers:
            merged = dict(self.session.headers)
            merged.update(headers)
            kwargs["headers"] = merged
        resp = self.session.request("GET", url, timeout=self.timeout, stream=True, **kwargs)
        try:
            resp.raise_for_status()
            content_length = int(resp.headers.get("Content-Length", "0") or 0)
            if content_length > max_bytes:
                raise ValueError(f"响应超过大小限制：{content_length} > {max_bytes}")
            chunks: list[bytes] = []
            total = 0
            iterator = getattr(resp, "iter_content", None)
            if callable(iterator):
                source = iterator(chunk_size=256 * 1024)
            else:
                source = [getattr(resp, "content", b"")]
            for chunk in source:
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"响应超过大小限制：{total} > {max_bytes}")
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            close = getattr(resp, "close", None)
            if callable(close):
                close()

    def close(self) -> None:
        self.session.close()

    def _request(
        self,
        method: str,
        url: str,
        *,
        retryable: bool | None = None,
        **kwargs,
    ) -> dict:
        """带有限重试的 JSON 请求；默认仅重试幂等 HTTP 方法。"""
        method = method.upper()
        if retryable is None:
            retryable = method in {"GET", "HEAD", "OPTIONS"}
        headers = kwargs.pop("headers", None)
        if headers:
            merged = dict(self.session.headers)
            merged.update(headers)
            kwargs["headers"] = merged

        last_error: Optional[Exception] = None
        attempts = self.max_retry if retryable else 0
        for attempt in range(attempts + 1):
            try:
                resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
                try:
                    resp.raise_for_status()
                    payload = resp.json()
                    raise_for_code(payload.get("code", 0), payload.get("message", ""))
                    return payload["data"]
                finally:
                    close = getattr(resp, "close", None)
                    if callable(close):
                        close()
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
