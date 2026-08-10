"""
统一请求层：BiliSession。

职责：
- 为所有 B 站 API 请求注入统一的 User-Agent / Referer / Cookie；
- 解析响应 JSON 并统一检查 code 字段（code != 0 抛异常）；
- 支持失败自动重试（替代旧代码里散落各处的 while 重试循环）。

[使用方法]
    session = BiliSession()                       # 使用默认 cookie（assets/cookie/qr_login.txt）
    data = session.get(VideoUrls.VIEW, params={"bvid": "BV1ov42117yC"})  # 返回 data 字典
"""

import logging
import time
from typing import Optional

import requests

from src.config.constants import MAX_RETRY, REQUEST_TIMEOUT, RETRY_DELAY
from src.config.cookie import BiliCookies
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
        :param cookie_path: cookie 文件路径。None 时使用全局默认 DEFAULT_COOKIE_PATH。
                            cookie 读取结果在 BiliCookies 内做进程级缓存。
        :param referer: 默认 Referer，可用 session.get/post 的 headers 参数覆盖。
        :param max_retry: 请求失败时的最大重试次数（不含首次）。
        :param timeout: 单次请求超时（秒）。
        """
        self.cookie = BiliCookies.from_file(cookie_path)
        self.referer = referer
        self.max_retry = max_retry
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.cookie.to_headers(referer=referer))

    # ---- 请求入口 ----

    def get(self, url: str, params: Optional[dict] = None, headers: Optional[dict] = None, **kwargs) -> dict:
        """GET 请求，返回业务 data 字段（dict）。"""
        return self._request("GET", url, params=params, headers=headers, **kwargs)

    def post(self, url: str, data: Optional[dict] = None, params: Optional[dict] = None,
             headers: Optional[dict] = None, **kwargs) -> dict:
        """POST 请求，返回业务 data 字段（dict）。"""
        return self._request("POST", url, data=data, params=params, headers=headers, **kwargs)

    def get_raw(self, url: str, headers: Optional[dict] = None, **kwargs) -> bytes:
        """GET 请求，返回原始二进制内容（用于下载封面、媒体流等非 JSON 资源）。"""
        if headers:
            merged = dict(self.session.headers)
            merged.update(headers)
            kwargs["headers"] = merged
        resp = self.session.request("GET", url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp.content

    # ---- 底层实现 ----

    def _request(self, method: str, url: str, **kwargs) -> dict:
        """带重试与错误检查的请求。成功返回 r_json["data"]。

        重试策略：仅对「网络/传输层」错误重试（连接失败、超时、HTTP 状态码、JSON 解析失败）；
        业务错误（BiliError，如未登录/风控/视频不存在）不重试，直接抛出。
        """
        headers = kwargs.pop("headers", None)
        if headers:
            merged = dict(self.session.headers)
            merged.update(headers)
            kwargs["headers"] = merged

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retry + 1):
            try:
                resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
                resp.raise_for_status()
                r_json = resp.json()
                raise_for_code(r_json.get("code", 0), r_json.get("message", ""))
                return r_json["data"]
            except (requests.RequestException, ValueError) as e:
                # 传输层/解析错误：记录并重试
                last_error = e
                logger.warning(
                    "[BiliSession-%s]第%d次请求%s失败：%s", method, attempt + 1, url, e
                )
            if attempt < self.max_retry:
                time.sleep(RETRY_DELAY)
        raise last_error if last_error is not None else RuntimeError(f"请求失败：{url}")
