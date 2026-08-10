"""鉴权（wbi 签名、设备ID、ticket）单元测试。"""

from unittest.mock import patch

import pytest

from src.api import auth
from src.api.auth import get_dev_id, get_timestamp, get_wbi, hmac_sha256


def test_dev_id_format():
    import re
    dev_id = get_dev_id()
    assert re.fullmatch(r"[0-9A-F]{8}-[0-9A-F]{4}-4[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}", dev_id)


def test_timestamp_int():
    assert isinstance(get_timestamp(), int)


def test_hmac_sha256_known():
    # HMAC-SHA256 已知向量
    assert hmac_sha256("key", "The quick brown fox jumps over the lazy dog") == (
        "f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8"
    )


# 至少 64 字符的假 img/sub key（mixin 表索引到 63）
FAKE_IMG_KEY = "0" * 64
FAKE_SUB_KEY = "1" * 64


def test_get_wbi_signed_params():
    params = {"bvid": "BV1ov42117yC", "foo": "114"}
    with patch("src.api.auth._get_wbi_keys", return_value=(FAKE_IMG_KEY, FAKE_SUB_KEY)):
        wts, w_rid = get_wbi(params)
    assert isinstance(wts, int)
    assert isinstance(w_rid, str) and len(w_rid) == 32  # md5 hex
    assert "wts" in params and "w_rid" in params


def test_get_wbi_without_params():
    with patch("src.api.auth._get_wbi_keys", return_value=(FAKE_IMG_KEY, FAKE_SUB_KEY)):
        wts, w_rid = get_wbi()
    assert isinstance(wts, int)
    assert len(w_rid) == 32


def test_get_wbi_keys_cached():
    """img/sub_key 应在进程内缓存，避免每次请求 nav。"""
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = {
            "data": {
                "wbi_img": {
                    "img_url": f"https://i0.hdslb.com/bfs/wbi/{FAKE_IMG_KEY}.png",
                    "sub_url": f"https://i0.hdslb.com/bfs/wbi/{FAKE_SUB_KEY}.png",
                }
            }
        }
        auth._wbi_keys_cache = None
        k1 = auth._get_wbi_keys()
        k2 = auth._get_wbi_keys()
        assert k1 == k2
        assert mock_get.call_count == 1  # 只请求一次
        auth._wbi_keys_cache = None  # 清理，避免影响其他测试
