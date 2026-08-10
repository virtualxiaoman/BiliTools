"""文件名清洗与命名规则的单元测试。"""

import pytest

from src.util.filename import (
    build_download_filename,
    build_multi_page_filename,
    resolve_save_path,
    sanitize_filename,
)


class TestSanitize:
    def test_removes_invalid_chars(self):
        # 反斜杠、斜杠、冒号、星号、问号、双引号、尖括号、竖线
        assert "a" in sanitize_filename(r"a\b/c:d*e?f\"g<h>i|j")
        assert all(ch not in sanitize_filename(r'a\b/c:d*e?f"g<h>i|j') for ch in r'\/*?"<>|')
        assert ":" not in sanitize_filename("a:b")

    def test_trims_whitespace_and_merges(self):
        assert sanitize_filename("  你好   世界  ") == "你好 世界"

    def test_strips_control_chars(self):
        assert sanitize_filename("a\x00b\x1fc") == "abc"

    def test_removes_trailing_dot_space(self):
        assert sanitize_filename("name.") == "name"
        assert sanitize_filename("name ") == "name"

    def test_windows_reserved_name(self):
        # 保留设备名会被加下划线前缀（保留原始大小写）
        assert sanitize_filename("CON") == "_CON"
        assert sanitize_filename("com1") == "_com1"
        # 带扩展名的名称不是保留设备名（保留名检查针对整个名称）
        assert sanitize_filename("NUL.txt") == "NUL.txt"

    def test_empty_falls_back(self):
        assert sanitize_filename("   ") == "untitled"

    def test_truncates_long(self):
        long_name = "啊" * 300
        assert len(sanitize_filename(long_name)) <= 255


class TestBuildFilename:
    def test_standard_format(self):
        assert build_download_filename("测试标题", "BV1ov42117yC") == "测试标题(BV1ov42117yC).mp4"

    def test_custom_ext(self):
        assert build_download_filename("测试", "BV1ov42117yC", "flv") == "测试(BV1ov42117yC).flv"

    def test_ext_with_dot(self):
        assert build_download_filename("测试", "BV1ov42117yC", ".m4a") == "测试(BV1ov42117yC).m4a"

    def test_invalid_chars_cleaned_in_title(self):
        assert build_download_filename('标题/含:非法?', "BV1ov42117yC") == "标题含非法(BV1ov42117yC).mp4"


class TestBuildMultiPageFilename:
    def test_standard(self):
        assert build_multi_page_filename("演唱会", "BV1Q43w6QETb", 2, "反乌托邦pt2") == \
            "演唱会-P02-反乌托邦pt2(BV1Q43w6QETb).mp4"

    def test_zero_padded_page(self):
        assert build_multi_page_filename("演唱会", "BV1Q43w6QETb", 9) == \
            "演唱会-P09(BV1Q43w6QETb).mp4"

    def test_custom_ext(self):
        assert build_multi_page_filename("演唱会", "BV1Q43w6QETb", 1, "第一P", "m4a") == \
            "演唱会-P01-第一P(BV1Q43w6QETb).m4a"

    def test_invalid_chars_in_part(self):
        assert build_multi_page_filename("演唱会", "BV1Q43w6QETb", 1, "标题/含:非法?") == \
            "演唱会-P01-标题含非法(BV1Q43w6QETb).mp4"


def test_resolve_save_path(tmp_path):
    path = resolve_save_path(tmp_path / "sub", "a.mp4")
    assert path == tmp_path / "sub" / "a.mp4"
    assert path.parent.exists()  # 目录被自动创建
