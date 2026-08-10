"""BV号/AV号转换的单元测试。"""

import pytest

from src.util.bvid import av2bv, bv2av

# 已知正确的对照（用代码反推验证，见测试里的 roundtrip）
KNOWN_PAIRS = [
    (170001, "BV17x411w7KC"),
    (455017605, "BV1Q541167Qg"),
    (1, "BV1xx411c7mQ"),
]


@pytest.mark.parametrize("aid,bvid", KNOWN_PAIRS)
def test_bv2av_known(aid, bvid):
    assert bv2av(bvid) == aid


@pytest.mark.parametrize("aid,bvid", KNOWN_PAIRS)
def test_av2bv_known(aid, bvid):
    assert av2bv(aid) == bvid


def test_roundtrip():
    """任意 av 号 bv 号互转一致。"""
    for aid in (1, 100, 100000, 1450404511):
        assert bv2av(av2bv(aid)) == aid


def test_lowercase_bv_prefix():
    """小写 bv 开头也应正确处理。"""
    assert bv2av("bv17x411w7KC") == 170001

def test_invalid_bv_raises():
    with pytest.raises(AssertionError):
        bv2av("not-a-bv")
