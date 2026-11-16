"""表情包/收藏集/装扮下载的终止检查（不联网）。"""

import threading

import pytest

from src.api.errors import DownloadCancelled
from src.services.dressup import DressupService
from src.services.emote import EmoteService
from src.services.garb import GarbService


def _cancelled():
    event = threading.Event()
    event.set()
    return event


def test_emote_cancel_before_start(tmp_path):
    service = EmoteService(session=object(), default_dir=tmp_path, cancel_event=_cancelled())
    with pytest.raises(DownloadCancelled):
        service.download_packages([1], tmp_path)


def test_garb_cancel_before_start(tmp_path):
    service = GarbService(session=object(), default_dir=tmp_path, cancel_event=_cancelled())
    with pytest.raises(DownloadCancelled):
        service.download_item({"name": "测试"}, tmp_path)


def test_dressup_cancel_before_start(tmp_path):
    service = DressupService(session=object(), default_dir=tmp_path, cancel_event=_cancelled())
    item = {"kind": "emoji", "name": "测试", "payload": {"id": 1}}
    with pytest.raises(DownloadCancelled):
        service.download_items([item], tmp_path)
