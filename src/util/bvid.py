"""
BV号与AV号的转换。
由旧 `src/utils.py` 中的 `BV2AV` 类迁移而来，改为模块级函数。
"""

from typing import Union

# 转化算法来自于 `BAC文档
# <https://socialsisteryi.github.io/bilibili-API-collect/docs/misc/bvid_desc.html#python>`_.
XOR_CODE = 23442827791579
MASK_CODE = 2251799813685247
MAX_AID = 1 << 51
ALPHABET = "FcwAPNKTMug3GV5Lj7EJnHpWsx4tb8haYeviqBz6rkCy12mUSDQX9RdoZf"
ENCODE_MAP = 8, 7, 0, 5, 1, 3, 2, 4, 6
DECODE_MAP = tuple(reversed(ENCODE_MAP))

BASE = len(ALPHABET)
PREFIX = "BV1"
PREFIX_LEN = len(PREFIX)
CODE_LEN = len(ENCODE_MAP)


def av2bv(aid: Union[int, str]) -> str:
    """
    [使用方法]:
        av2bv(111298867365120)  # 返回"BV1L9Uoa9EUx"
    :param aid: av号（整数或数字字符串）
    :return: bv号
    """
    aid = int(aid)
    bvid = [""] * 9
    tmp = (MAX_AID | aid) ^ XOR_CODE
    for i in range(CODE_LEN):
        bvid[ENCODE_MAP[i]] = ALPHABET[tmp % BASE]
        tmp //= BASE
    return PREFIX + "".join(bvid)


def bv2av(bvid: str) -> int:
    """
    [使用方法]:
        bv2av("BV1L9Uoa9EUx")  # 返回111298867365120
    :param bvid: bv号（BV 或 bv 开头均可）
    :return: av号
    """
    if bvid[:2] == "bv":
        bvid = "BV" + bvid[2:]
    assert bvid[:PREFIX_LEN] == PREFIX, f"非法的 BV 号：{bvid}"
    bvid = bvid[PREFIX_LEN:]
    tmp = 0
    for i in range(CODE_LEN):
        idx = ALPHABET.index(bvid[DECODE_MAP[i]])
        tmp = tmp * BASE + idx
    return (tmp & MASK_CODE) ^ XOR_CODE
