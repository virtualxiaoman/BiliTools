"""ReplyService 评论获取单元测试（不联网）。"""

import pytest

from src.services.reply import ReplyService
from src.urls.comment_urls import CommentUrls
from src.util.bvid import bv2av


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, params=None, headers=None):
        self.calls.append((url, params, headers))
        return {"replies": self.pages.get(params["pn"], [])}


def _comment(rpid):
    return {"rpid": rpid, "content": {"message": f"评论 {rpid}"}}


def test_get_comments_paginates_and_limits_count():
    session = FakeSession({
        1: [_comment(i) for i in range(1, 21)],
        2: [_comment(i) for i in range(21, 41)],
    })
    service = ReplyService(session)

    comments = service.get_comments(
        bvid="BV1ov42117yC", sort="hot", max_count=25
    )

    assert len(comments) == 25
    assert [c["rpid"] for c in comments[:2]] == [1, 2]
    assert session.calls[0][0] == CommentUrls.LIST
    assert session.calls[0][1] == {
        "type": 1,
        "oid": bv2av("BV1ov42117yC"),
        "sort": 1,
        "pn": 1,
        "ps": 20,
    }
    assert session.calls[1][1]["pn"] == 2


def test_get_comments_unlimited_stops_at_short_page_and_supports_aid():
    session = FakeSession({
        1: [_comment(i) for i in range(1, 4)],
    })
    service = ReplyService(session)

    comments = service.get_replies(aid=123, sort="最新")

    assert len(comments) == 3
    assert session.calls[0][1] == {
        "type": 1,
        "oid": 123,
        "sort": 0,
        "pn": 1,
        "ps": 20,
    }
    assert session.calls[0][2] is None


def test_get_comments_zero_does_not_request():
    session = FakeSession({})
    assert ReplyService(session).get_video_comments(aid=123, max_count=0) == []
    assert session.calls == []


@pytest.mark.parametrize("kwargs", [
    {"max_count": -2},
    {"page_size": 0},
    {"sort": "unknown"},
])
def test_get_comments_rejects_invalid_options(kwargs):
    with pytest.raises(ValueError):
        ReplyService(FakeSession({})).get_comments(aid=123, **kwargs)


def test_get_comments_requires_video_identifier():
    with pytest.raises(ValueError):
        ReplyService(FakeSession({})).get_comments()
