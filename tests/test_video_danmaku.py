"""VideoService danmaku ASS 下载单元测试（不联网）。"""

import zlib

from src.models import VideoInfo, VideoPage
from src.services.video import VideoService
from src.urls.video_urls import VideoUrls


class FakeRawSession:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def get_raw(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.content


def _service(tmp_path, content, info):
    service = VideoService.__new__(VideoService)
    service.default_dir = tmp_path
    service.session = FakeRawSession(content)
    service.fetch_info = lambda bvid: info
    return service


def test_download_danmaku_uses_cid_and_video_filename(tmp_path):
    bvid = "BV1test123"
    info = VideoInfo(
        bvid=bvid, title="Test video", cid=987,
        pages=[VideoPage(page=1, cid=987, part="Test video")],
    )
    xml = b'<?xml version="1.0" encoding="UTF-8"?><i><d p="1,1,36,16777215">danmaku</d></i>'
    session = FakeRawSession(zlib.compress(xml))
    service = _service(tmp_path, session.content, info)

    result = service.download_danmaku(bvid, tmp_path, progress_cb=lambda *_: None)

    assert result.path.name == "Test video(BV1test123).ass"
    ass = result.path.read_text(encoding="utf-8-sig")
    assert "[Events]" in ass
    assert "Dialogue: 0,0:00:01.00,0:00:09.00" in ass
    assert "danmaku" in ass
    assert result.media_type == "danmaku"
    assert result.cached is False
    assert service.session.calls[0][0] == VideoUrls.DANMAKU
    assert service.session.calls[0][1]["params"] == {"oid": 987}


def test_download_danmaku_multi_page_keeps_page_name(tmp_path):
    bvid = "BVmulti123"
    info = VideoInfo(
        bvid=bvid, title="Collection", cid=1,
        pages=[VideoPage(page=1, cid=1, part="Part one"), VideoPage(page=2, cid=2, part="Part two")],
    )
    xml = b"<i><d p=\"1\">dm</d></i>"
    service = _service(tmp_path, xml, info)

    result = service.download_danmaku(bvid, tmp_path, page=2, progress_cb=lambda *_: None)

    assert result.path.name == "Collection-P02-Part two(BVmulti123).ass"
    assert result.path.read_text(encoding="utf-8-sig").startswith("[Script Info]")
    assert service.session.calls[0][1]["params"] == {"oid": 2}


def test_download_danmaku_reuses_cached_xml(tmp_path):
    bvid = "BVcache123"
    info = VideoInfo(bvid=bvid, title="Title", cid=1, pages=[])
    cached = tmp_path / "Title(BVcache123).ass"
    cached.write_bytes(b"<i/>")
    service = _service(tmp_path, b"should not be requested", info)

    result = service.download_danmaku(bvid, tmp_path)

    assert result.path == cached
    assert result.cached is True
    assert service.session.calls == []


def test_download_danmaku_can_keep_xml_format(tmp_path):
    bvid = "BVxml123"
    info = VideoInfo(bvid=bvid, title="XML", cid=1, pages=[])
    xml = b"<i><d p=\"1,1,25,16777215\">dm</d></i>"
    service = _service(tmp_path, xml, info)

    result = service.download_danmaku(bvid, tmp_path, format="xml", progress_cb=lambda *_: None)

    assert result.path.name == "XML(BVxml123).xml"
    assert result.path.read_bytes() == xml
