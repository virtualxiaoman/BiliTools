"""
鉴权工具：wbi 签名、设备 ID、bilibili ticket。

由旧 `src/utils.py` 中的 `AuthUtil` 与 `hmac_sha256` 迁移而来，
逻辑保持一致，仅将实例方法收敛为静态方法/模块级函数。
"""

import hashlib
import hmac
import random
import time
import urllib.parse
from functools import reduce
from typing import Optional

import requests

from src.config.constants import API_BASE, UserAgent

# wbi 签名所需的 img_key / sub_key 缓存（进程内，长时间有效）
_wbi_keys_cache: Optional[tuple[str, str]] = None


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
    """获取最新的 img_key 和 sub_key（带进程内缓存）"""
    global _wbi_keys_cache
    if _wbi_keys_cache is not None:
        return _wbi_keys_cache
    headers = {
        'User-Agent': UserAgent().pcChrome,
        'Referer': 'https://www.bilibili.com/'
    }
    resp = requests.get(f"{API_BASE}/x/web-interface/nav", headers=headers)
    resp.raise_for_status()
    json_content = resp.json()
    img_url: str = json_content['data']['wbi_img']['img_url']
    sub_url: str = json_content['data']['wbi_img']['sub_url']
    img_key = img_url.rsplit('/', 1)[1].split('.')[0]
    sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
    _wbi_keys_cache = (img_key, sub_key)
    return _wbi_keys_cache


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
