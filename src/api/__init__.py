"""
Bilibili API 层：统一请求、签名、错误处理。

- `errors.py`  统一异常体系
- `auth.py`    wbi 签名、设备 ID、bilibili ticket
- `session.py` BiliSession：统一的请求入口（重试、错误检查、Cookie 注入）
"""

from src.api.session import BiliSession

__all__ = ["BiliSession"]
