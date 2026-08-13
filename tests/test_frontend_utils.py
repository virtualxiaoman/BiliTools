"""前端输入归一化单元测试（无网络，避免落到 normalize_bvid 的链接请求分支）。"""
from frontend.pyside6.utils import extract_page_from_url, normalize_season


def test_normalize_season_lists_url():
    """合集空间链接 /mid/lists/sid：按路径结构提取，不依赖 ?type=season。"""
    assert normalize_season("https://space.bilibili.com/506925078/lists/1717000?type=season") \
        == ("sid", 1717000, 506925078)
    assert normalize_season("https://space.bilibili.com/506925078/lists/1717000") \
        == ("sid", 1717000, 506925078)


def test_normalize_season_sid_param():
    assert normalize_season("https://space.bilibili.com/506925078/channel/collectiondetail?sid=1717000") \
        == ("sid", 1717000, 506925078)


def test_normalize_season_plain_sid():
    assert normalize_season("8683221") == ("sid", 8683221, 0)


def test_normalize_season_bvid():
    assert normalize_season("BV1Q43w6QETb") == ("bvid", "BV1Q43w6QETb", None)


def test_extract_page_from_url():
    assert extract_page_from_url(
        "https://www.bilibili.com/video/BV1ws411v7zE?spm_id_from=333&vd_source=x&p=2") == 2
    assert extract_page_from_url("https://www.bilibili.com/video/BV1ws411v7zE") is None
    assert extract_page_from_url("BV1ws411v7zE") is None
