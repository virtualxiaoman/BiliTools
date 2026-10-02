"""ReplyService 评论获取单元测试（不联网）。"""

import pytest

from src.services.reply import ReplyService
from src.urls.comment_urls import CommentUrls
from src.util.bvid import bv2av


class FakeSession:
    def __init__(self, pages, dynamic_detail=None):
        self.pages = pages
        self.dynamic_detail = dynamic_detail
        self.calls = []

    def get(self, url, params=None, headers=None):
        self.calls.append((url, params, headers))
        if url == CommentUrls.DYNAMIC_DETAIL:
            return self.dynamic_detail or {}
        return {"replies": self.pages.get(params["pn"], [])}


def _comment(rpid):
    return {"rpid": rpid, "content": {"message": f"评论 {rpid}"}}


def test_get_comments_paginates_and_limits_count():
    session = FakeSession({
        1: [_comment(i) for i in range(1, 21)],
        2: [_comment(i) for i in range(21, 41)],
    })
    service = ReplyService(session)

    comments = service.get_video_comments(
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


def test_get_comments_keeps_legacy_video_alias():
    session = FakeSession({1: [_comment(1)]})

    comments = ReplyService(session).get_comments(aid=123)

    assert [comment["rpid"] for comment in comments] == [1]


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


def test_get_dynamic_comments_resolves_opus_comment_id_and_type():
    session = FakeSession(
        {1: [_comment(101), _comment(102)]},
        dynamic_detail={
            "item": {
                "basic": {
                    "comment_id_str": "379334304",
                    "comment_type": 11,
                },
            },
        },
    )

    comments = ReplyService(session).get_dynamic_comments(
        "https://www.bilibili.com/opus/1151100571637252104",
        sort="hot",
        max_count=10,
    )

    assert len(comments) == 2
    assert session.calls[0][0] == CommentUrls.DYNAMIC_DETAIL
    assert session.calls[0][1] == {"id": 1151100571637252104}
    assert session.calls[1][1] == {
        "type": 11,
        "oid": 379334304,
        "sort": 1,
        "pn": 1,
        "ps": 20,
    }


def test_get_opus_comments_supports_dynamic_alias():
    session = FakeSession(
        {1: [_comment(1)]},
        dynamic_detail={
            "item": {"basic": {"comment_id": 123, "comment_type": 17}},
        },
    )

    assert len(ReplyService(session).get_opus_comments(456)) == 1
    assert session.calls[1][1]["type"] == 17
    assert session.calls[1][1]["oid"] == 123


def test_get_dynamic_comments_rejects_invalid_detail():
    with pytest.raises(ValueError):
        ReplyService(FakeSession({}, dynamic_detail={"item": {}})).get_dynamic_comments(1)


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
        ReplyService(FakeSession({})).get_video_comments(aid=123, **kwargs)


def test_get_comments_requires_video_identifier():
    with pytest.raises(ValueError):
        ReplyService(FakeSession({})).get_video_comments()


def test_get_comments_by_oid_public_entry_skips_detail_request():
    """公共入口直接消费已知的 comment_id_str/comment_type，不再请求动态详情。"""
    session = FakeSession({1: [_comment(1), _comment(2)]})

    comments = ReplyService(session).get_comments_by_oid(409870383, 11, sort="hot", max_count=20)

    assert [c["rpid"] for c in comments] == [1, 2]
    assert len(session.calls) == 1
    assert session.calls[0][0] == CommentUrls.LIST
    assert session.calls[0][1] == {
        "type": 11,
        "oid": 409870383,
        "sort": 1,
        "pn": 1,
        "ps": 20,
    }
