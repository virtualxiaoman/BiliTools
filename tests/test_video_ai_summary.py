"""VideoService 视频 AI 总结单元测试。"""

from dataclasses import is_dataclass
from unittest.mock import patch

import pytest

from src.models import VideoAISummary, VideoAISummaryOutline, VideoAISummarySubtitle
from src.services.video import VideoService
from src.urls.video_urls import VideoUrls


class FakeSession:
    def __init__(self, summary_data, view_data=None):
        self.summary_data = summary_data
        self.view_data = view_data
        self.calls = []

    def get(self, url, params=None, headers=None):
        self.calls.append((url, params, headers))
        if url == VideoUrls.VIEW:
            return self.view_data or {}
        if url == VideoUrls.AI_SUMMARY:
            return self.summary_data
        raise AssertionError(f"unexpected URL: {url}")


def _summary_data():
    return {
        "code": 0,
        "stid": "stid-1",
        "status": 1,
        "like_num": 2,
        "dislike_num": 3,
        "model_result": {
            "result_type": 2,
            "summary": "这是视频摘要。",
            "outline": [{
                "title": "第一部分",
                "timestamp": 1,
                "part_outline": [{"timestamp": 2, "content": "要点"}],
            }],
            "subtitle": [{
                "timestamp": 1,
                "title": "字幕",
                "part_subtitle": [{
                    "content": "你好",
                    "start_timestamp": 1,
                    "end_timestamp": 2,
                }],
            }],
        },
    }


def test_fetch_ai_summary_returns_nested_dataclasses_and_signs_params():
    session = FakeSession(_summary_data())
    service = VideoService(session=session)

    with patch("src.services.video.get_wbi", side_effect=lambda params: params.update(wts=123, w_rid="rid")):
        result = service.fetch_ai_summary(bvid="BV1test", cid=987)

    assert is_dataclass(result)
    assert isinstance(result, VideoAISummary)
    assert result.summary_text == "这是视频摘要。"
    assert isinstance(result.model_result.outline[0], VideoAISummaryOutline)
    assert result.model_result.outline[0].part_outline[0].content == "要点"
    assert isinstance(result.model_result.subtitle[0], VideoAISummarySubtitle)
    assert result.model_result.subtitle[0].part_subtitle[0].end_timestamp == 2
    assert session.calls[0][0] == VideoUrls.AI_SUMMARY
    assert session.calls[0][1] == {
        "cid": 987,
        "bvid": "BV1test",
        "wts": 123,
        "w_rid": "rid",
    }


def test_fetch_ai_summary_auto_resolves_cid_and_up_mid_from_view():
    session = FakeSession(
        _summary_data(),
        view_data={
            "bvid": "BV1test",
            "aid": 100,
            "pages": [{"cid": 456}],
            "owner": {"mid": 789, "name": "UP"},
        },
    )
    service = VideoService(session=session)

    with patch("src.services.video.get_wbi", side_effect=lambda params: params.update(wts=123, w_rid="rid")):
        result = service.fetch_ai_summary(bvid="BV1test")

    assert result.summary_text == "这是视频摘要。"
    assert session.calls[0][1] == {"bvid": "BV1test"}
    assert session.calls[1][1]["cid"] == 456
    assert session.calls[1][1]["up_mid"] == 789


def test_fetch_ai_summary_text_returns_string():
    session = FakeSession(_summary_data())
    service = VideoService(session=session)

    with patch("src.services.video.get_wbi", side_effect=lambda params: params.update(wts=123, w_rid="rid")):
        text = service.get_ai_summary_text(bvid="BV1test", cid=987)

    assert isinstance(text, str)
    assert text == "这是视频摘要。"


@pytest.mark.parametrize("kwargs", [
    {},
    {"bvid": "BV1", "aid": 1},
    {"bvid": "BV1", "cid": 0},
    {"aid": -1, "cid": 1},
])
def test_fetch_ai_summary_rejects_invalid_identifiers(kwargs):
    with pytest.raises(ValueError):
        VideoService(session=FakeSession(_summary_data())).fetch_ai_summary(**kwargs)
