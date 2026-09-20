"""网络访问 URL 日志的单元测试。"""

import logging
from types import SimpleNamespace

from src.api.session import BiliSession
from src.services.garb import GarbService
from src.util.downloader import download_stream


class _JsonResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"code": 0, "data": {"ok": True}}

    def close(self):
        pass


class _RequestSession:
    headers = {}

    def request(self, *args, **kwargs):
        return _JsonResponse()

    def close(self):
        pass


def test_bili_session_logs_full_url_with_query_parameters(caplog):
    client = object.__new__(BiliSession)
    client.session = _RequestSession()
    client.timeout = 1
    client.max_retry = 0

    with caplog.at_level(logging.DEBUG, logger="src.api.session"):
        assert client.get("https://api.example.test/view", params={"bvid": "BV 1", "page": 2}) == {"ok": True}

    assert "[BiliSession-GET] 访问 URL：https://api.example.test/view?bvid=BV+1&page=2" in caplog.text


def test_media_download_logs_url_before_request(tmp_path, monkeypatch, caplog):
    class _StreamResponse:
        headers = {"Content-Length": "2"}
        status_code = 200

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield b"ok"

        def close(self):
            pass

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: _StreamResponse())

    with caplog.at_level(logging.DEBUG, logger="src.util.downloader"):
        assert download_stream("https://cdn.example.test/collection/cover.jpg?token=abc", tmp_path / "cover.jpg") == 2

    assert "[download_stream] 访问 URL：https://cdn.example.test/collection/cover.jpg?token=abc" in caplog.text


def test_collection_download_writes_its_resource_url_to_log(tmp_path, monkeypatch, caplog):
    class _CollectionSession:
        session = SimpleNamespace(headers={})

    class _StreamResponse:
        headers = {"Content-Length": "2"}
        status_code = 200

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield b"ok"

        def close(self):
            pass

    class _Progress:
        def start(self, *args):
            pass

        def finish(self):
            pass

        def make_stream_callback(self):
            return None

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: _StreamResponse())
    item = {"name": "测试收藏集", "part_id": 0}
    detail = {"cover": "https://cdn.example.test/collection/cover.jpg?token=abc"}

    with caplog.at_level(logging.DEBUG, logger="src.util.downloader"):
        results = GarbService(_CollectionSession()).download_item(
            item, tmp_path, detail=detail, progress=_Progress(),
        )

    assert len(results) == 1
    assert "[download_stream] 访问 URL：https://cdn.example.test/collection/cover.jpg?token=abc" in caplog.text
