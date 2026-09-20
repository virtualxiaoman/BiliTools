"""
鉴权工具：wbi 签名、设备 ID、bilibili ticket。

由旧 `src/utils.py` 中的 `AuthUtil` 与 `hmac_sha256` 迁移而来，
逻辑保持一致，仅将实例方法收敛为静态方法/模块级函数。
"""

import hashlib
import logging
import hmac
import random
import threading
import time
import urllib.parse
from functools import reduce
from typing import Optional

import requests

from src.config.constants import API_BASE, UserAgent

logger = logging.getLogger(__name__)

# wbi 签名所需的 img_key / sub_key 缓存（进程内，长时间有效）
_wbi_keys_cache: Optional[tuple[str, str, float]] = None
_WBI_LOCK = threading.Lock()
_WBI_TTL = 3600.0


def get_dev_id() -> str:
    """
    获取设备 ID(可以自行在浏览器中查看)
    [使用方法]:
        print(get_dev_id())
    :return: 设备 ID
    """
    b = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F']
    s = list("xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx")
    for i in range(len(s)):
        if s[i] == '-' or s[i] == '4':
            continue
        random_int = random.randint(0, 15)
        if s[i] == 'x':
            s[i] = b[random_int]
        else:
            s[i] = b[(3 & random_int) | 8]
    return ''.join(s)  # 得到B182F410-3865-46ED-840F-B58B71A78B5E这样的


def get_timestamp() -> int:
    """
    获取时间戳
    [使用方法]:
        print(get_timestamp())
    :return: 时间戳
    """
    return int(time.time())


def _get_mixin_key(orig: str) -> str:
    """对 imgKey 和 subKey 进行字符顺序打乱编码"""
    mixin_key_enc_tab = [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
        33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
        61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
        36, 20, 34, 44, 52
    ]
    return reduce(lambda s, i: s + orig[i], mixin_key_enc_tab, '')[:32]


def _enc_wbi(params: dict, img_key: str, sub_key: str) -> dict:
    """为请求参数进行 wbi 签名"""
    mixin_key = _get_mixin_key(img_key + sub_key)
    curr_time = round(time.time())
    params['wts'] = curr_time  # 添加 wts 字段
    params = dict(sorted(params.items()))  # 按照 key 重排参数
    # 过滤 value 中的 "!'()*" 字符
    params = {
        k: ''.join(filter(lambda chr: chr not in "!'()*", str(v)))
        for k, v
        in params.items()
    }
    query = urllib.parse.urlencode(params)  # 序列化参数
    wbi_sign = hashlib.md5((query + mixin_key).encode()).hexdigest()  # 计算 w_rid
    params['w_rid'] = wbi_sign
    return params


def _get_wbi_keys() -> tuple[str, str]:
    """获取带 TTL 的 WBI key；并发首次加载只允许一个网络请求。"""
    global _wbi_keys_cache
    with _WBI_LOCK:
        now = time.monotonic()
        if _wbi_keys_cache is not None and now - _wbi_keys_cache[2] < _WBI_TTL:
            return _wbi_keys_cache[0], _wbi_keys_cache[1]
        headers = {
            "User-Agent": UserAgent().pcChrome,
            "Referer": "https://www.bilibili.com/",
        }
        last_error = None
        for attempt in range(3):
            try:
                logger.debug("[WBI] 访问 URL：%s/x/web-interface/nav", API_BASE)
                resp = requests.get(
                    f"{API_BASE}/x/web-interface/nav",
                    headers=headers,
                    timeout=(10, 30),
                )
                try:
                    resp.raise_for_status()
                    payload = resp.json()
                finally:
                    close = getattr(resp, "close", None)
                    if callable(close):
                        close()
                wbi = payload.get("data", {}).get("wbi_img", {})
                img_url, sub_url = wbi.get("img_url"), wbi.get("sub_url")
                if not isinstance(img_url, str) or not isinstance(sub_url, str):
                    raise ValueError("WBI 响应缺少 img_url/sub_url")
                img_key = img_url.rsplit("/", 1)[-1].split(".", 1)[0]
                sub_key = sub_url.rsplit("/", 1)[-1].split(".", 1)[0]
                if not img_key or not sub_key:
                    raise ValueError("WBI key 为空")
                _wbi_keys_cache = (img_key, sub_key, time.monotonic())
                return img_key, sub_key
            except (requests.RequestException, ValueError, KeyError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.2 * (2 ** attempt) + random.uniform(0, 0.1))
        raise last_error or RuntimeError("WBI key 获取失败")


def get_wbi(params: Optional[dict] = None) -> tuple[int, str]:
    """
    获取 wbi 签名后的鉴权参数（wts 时间戳 + w_rid 签名）。

    [使用方法]:
        wts, w_rid = get_wbi()
        # 或对已有参数进行签名：params = {"bvid": "BV1ov42117yC"}; get_wbi(params)
    :param params: 需要签名的业务参数。传入时会在原地追加 wts 与 w_rid（与旧 AuthUtil 行为一致）
    :return: (wts, w_rid)，wts 为整数时间戳
    """
    if params is None:
        params = {}
    # 业务参数（例如 bvid/cid/fnval）先由调用方放入 params，再在这里追加
    # wts/w_rid；调用方随后把同一个 dict 交给 BiliSession，签名参数不会丢失。
    img_key, sub_key = _get_wbi_keys()
    signed_params = _enc_wbi(params=params, img_key=img_key, sub_key=sub_key)
    # _enc_wbi 已在原 dict 上追加 wts/w_rid；signed_params 与 params 是同一对象
    params.update(signed_params)
    wts = signed_params.get('wts')
    w_rid = signed_params.get('w_rid')
    if wts is not None:
        wts = int(wts)
    return wts, w_rid


def hmac_sha256(key: str, message: str) -> str:
    """
    使用HMAC-SHA256算法对给定的字符串进行加密
    :param key: 密钥
    :param message: 要加密的消息
    :return: 加密后的哈希值(hex字符串)
    """
    hash_value = hmac.new(key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).digest()
    return hash_value.hex()
