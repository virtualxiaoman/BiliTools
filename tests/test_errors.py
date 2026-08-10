"""异常体系的单元测试。"""

import pytest

from src.api.errors import (
    BiliAPIError,
    BiliAuthError,
    BiliError,
    BiliForbiddenError,
    BiliRiskError,
    DownloadError,
    FFmpegNotFoundError,
    VideoNotFoundError,
    raise_for_code,
)


def test_code_zero_noop():
    assert raise_for_code(0, "ok") is None


@pytest.mark.parametrize("code,exc", [
    (-101, BiliAuthError),
    (-403, BiliForbiddenError),
    (-412, BiliRiskError),
    (-404, VideoNotFoundError),
    (-1, BiliAPIError),
    (1000, BiliAPIError),
])
def test_code_mapping(code, exc):
    with pytest.raises(exc):
        raise_for_code(code, "msg")


def test_all_errors_inherit_base():
    for exc in (BiliAuthError, BiliForbiddenError, BiliRiskError, BiliAPIError,
                VideoNotFoundError, DownloadError, FFmpegNotFoundError):
        assert issubclass(exc, BiliError)


def test_bili_api_error_message():
    err = BiliAPIError(-352, "风控校验失败")
    assert "风控校验失败" in str(err)
    assert err.code == -352


def test_video_not_found_is_api_error():
    assert issubclass(VideoNotFoundError, BiliAPIError)
