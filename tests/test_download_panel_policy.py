"""下载面板：多账号大会员提示的触发条件。"""

from frontend.pyside6.widgets.download_panel import DownloadPanel


def _spec(**overrides):
    spec = {
        "source": "up",
        "scope": "all",
        "quality": 120,
        "threads": 2,
        "distribute_accounts": True,
    }
    spec.update(overrides)
    return spec


def test_prompt_for_multi_account_high_quality():
    assert DownloadPanel._needs_account_quality_prompt(_spec()) is True
    assert DownloadPanel._needs_account_quality_prompt(_spec(source="fav")) is True
    assert DownloadPanel._needs_account_quality_prompt(_spec(source="season")) is True
    assert DownloadPanel._needs_account_quality_prompt(_spec(source="bv", scope="all")) is True


def test_no_prompt_for_1080p_or_lower():
    assert DownloadPanel._needs_account_quality_prompt(_spec(quality=80)) is False
    assert DownloadPanel._needs_account_quality_prompt(_spec(quality=64)) is False


def test_no_prompt_without_distribution():
    assert DownloadPanel._needs_account_quality_prompt(_spec(distribute_accounts=False)) is False
    assert DownloadPanel._needs_account_quality_prompt(_spec(threads=1)) is False


def test_no_prompt_for_single_video_or_non_video_sources():
    assert DownloadPanel._needs_account_quality_prompt(_spec(source="bv", scope="single")) is False
    assert DownloadPanel._needs_account_quality_prompt(_spec(source="emote")) is False
    assert DownloadPanel._needs_account_quality_prompt(_spec(source="dressup")) is False
