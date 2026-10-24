"""ReplyService 评论获取单元测试（不联网）。"""

import json

import pytest

from src.api.errors import BiliAPIError
from src.services.reply import ReplyService
from src.urls.comment_urls import CommentUrls
from src.util.bvid import av2bv, bv2av


class FakeSession:
    def __init__(self, pages, dynamic_detail=None, sub_pages=None,
                 pinned=None, errors=None):
        self.pages = pages
        self.dynamic_detail = dynamic_detail
        self.sub_pages = sub_pages or {}
        self.pinned = pinned or []
        self.errors = errors or {}
        self.calls = []

    def get(self, url, params=None, headers=None):
        self.calls.append((url, params, headers))
        if url == CommentUrls.DYNAMIC_DETAIL:
            return self.dynamic_detail or {}
        if url == CommentUrls.SUB_REPLY:
            if params["root"] in self.errors:
                raise self.errors[params["root"]]
            root_pages = {
                page: replies
                for (root, page), replies in self.sub_pages.items()
                if root == params["root"]
            }
            return {
                "replies": root_pages.get(params["pn"], []),
                "page": {"count": sum(len(replies) for replies in root_pages.values())},
            }
        return {
            "replies": self.pages.get(params["pn"], []),
            "top_replies": self.pinned,
        }


def _comment(rpid):
    return {"rpid": rpid, "content": {"message": f"评论 {rpid}"}}


def _detailed_comment(rpid, uname, message, *, parent=0, ctime=1700000000, like=0):
    return {
        "rpid": rpid,
        "parent": parent,
        "ctime": ctime,
        "like": like,
        "member": {"uname": uname, "mid": rpid},
        "content": {"message": message},
    }


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


def test_get_comments_unlimited_continues_after_short_page_and_supports_aid():
    """中间页被删除/折叠评论压到不足 20 条时，不能误判为末页。"""
    session = FakeSession({
        1: [_comment(1), _comment(2)],
        2: [_comment(3)],
    })
    service = ReplyService(session)

    comments = service.get_replies(aid=123, sort="最新")

    assert [comment["rpid"] for comment in comments] == [1, 2, 3]
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
    assert [call[1]["pn"] for call in session.calls] == [1, 2]
    assert session.calls[0][0] == CommentUrls.LIST
    assert session.calls[0][1] == {
        "type": 11,
        "oid": 409870383,
        "sort": 1,
        "pn": 1,
        "ps": 20,
    }


def test_get_comments_merges_pinned_and_dedupes():
    session = FakeSession(
        {1: [_comment(1), _comment(2)]},
        pinned=[_comment(1)],
    )

    comments = ReplyService(session).get_video_comments(aid=123)

    assert [c["rpid"] for c in comments] == [1, 2]
    assert comments[0]["is_pinned"] is True
    assert "is_pinned" not in comments[1]


def test_get_comments_pinned_counts_toward_max_count():
    session = FakeSession(
        {1: [_comment(1), _comment(2)]},
        pinned=[_comment(99)],
    )

    comments = ReplyService(session).get_video_comments(aid=123, max_count=1)

    assert [c["rpid"] for c in comments] == [99]


def test_get_comment_replies_paginates_all():
    session = FakeSession({}, sub_pages={
        (9, 1): [_comment(i) for i in range(1, 21)],
        (9, 2): [_comment(i) for i in range(21, 23)],
    })

    replies = ReplyService(session).get_comment_replies(oid=123, root=9)

    assert [r["rpid"] for r in replies] == list(range(1, 23))
    assert session.calls[0][0] == CommentUrls.SUB_REPLY
    assert session.calls[-1][1] == {
        "type": 1,
        "oid": 123,
        "root": 9,
        "pn": 2,
        "ps": 20,
    }


def test_get_video_comments_expands_sub_replies():
    root = _comment(9)
    root["rcount"] = 3
    root["replies"] = [_comment(101)]
    session = FakeSession({1: [root]}, sub_pages={
        (9, 1): [_comment(101), _comment(102), _comment(103)],
    })

    comments = ReplyService(session).get_video_comments(
        aid=123, with_sub_replies=True
    )

    assert [r["rpid"] for r in comments[0]["replies"]] == [101, 102, 103]
    assert session.calls[-1][0] == CommentUrls.SUB_REPLY
    assert session.calls[-1][1] == {
        "type": 1,
        "oid": 123,
        "root": 9,
        "pn": 1,
        "ps": 20,
    }


def test_sub_replies_skip_request_when_inline_is_complete():
    root = _comment(9)
    root["rcount"] = 1
    root["replies"] = [_comment(101)]
    session = FakeSession({1: [root]})

    comments = ReplyService(session).get_video_comments(
        aid=123, with_sub_replies=True
    )

    assert all(call[0] == CommentUrls.LIST for call in session.calls)
    assert [r["rpid"] for r in comments[0]["replies"]] == [101]


def test_sub_reply_api_error_keeps_inline_replies():
    root = _comment(9)
    root["rcount"] = 5
    root["replies"] = [_comment(101)]
    session = FakeSession(
        {1: [root]},
        errors={9: BiliAPIError(12002, "评论不存在")},
    )

    comments = ReplyService(session).get_video_comments(
        aid=123, with_sub_replies=True
    )

    assert [r["rpid"] for r in comments[0]["replies"]] == [101]


def test_sub_reply_max_count_truncates():
    root = _comment(9)
    root["rcount"] = 30
    root["replies"] = []
    session = FakeSession({1: [root]}, sub_pages={
        (9, 1): [_comment(i) for i in range(1, 21)],
        (9, 2): [_comment(i) for i in range(21, 31)],
    })

    comments = ReplyService(session).get_video_comments(
        aid=123, with_sub_replies=True, sub_max_count=25
    )

    assert len(comments[0]["replies"]) == 25
    sub_calls = [call for call in session.calls if call[0] == CommentUrls.SUB_REPLY]
    assert [call[1]["pn"] for call in sub_calls] == [1, 2]


def test_get_dynamic_comments_supports_sub_replies():
    root = _comment(9)
    root["rcount"] = 2
    root["replies"] = []
    session = FakeSession(
        {1: [root]},
        dynamic_detail={
            "item": {"basic": {"comment_id_str": "379", "comment_type": 11}},
        },
        sub_pages={(9, 1): [_comment(101), _comment(102)]},
    )

    comments = ReplyService(session).get_opus_comments(456, with_sub_replies=True)

    assert [r["rpid"] for r in comments[0]["replies"]] == [101, 102]


@pytest.mark.parametrize("kwargs", [
    {"sub_max_count": -2},
    {"sub_page_size": 0},
])
def test_get_comments_rejects_invalid_sub_options(kwargs):
    with pytest.raises(ValueError):
        ReplyService(FakeSession({})).get_video_comments(
            aid=123, with_sub_replies=True, **kwargs
        )


def test_export_video_comments_writes_json_and_markdown(tmp_path):
    pinned = _detailed_comment(99, "置顶用户", "置顶评论", like=10)
    pinned.update({"rcount": 0, "replies": []})
    root = _detailed_comment(9, "根用户", "根评论第一行\n第二行", like=12)
    root.update({"rcount": 2, "replies": []})
    reply1 = _detailed_comment(101, "子用户", "子评论", parent=9, ctime=1700000100, like=3)
    reply2 = _detailed_comment(102, "孙用户", "回复子评论", parent=101, ctime=1700000200)
    session = FakeSession(
        {1: [root]},
        pinned=[pinned],
        sub_pages={(9, 1): [reply1, reply2]},
    )

    result = ReplyService(session).export_video_comments(
        bvid="BV1ov42117yC", sort="hot", save_dir=tmp_path
    )

    assert result.export_dir == tmp_path / "BV1ov42117yC"
    assert result.bvid == "BV1ov42117yC"
    assert result.aid == bv2av("BV1ov42117yC")
    assert result.sort == "hot"
    assert result.root_count == 2
    assert result.sub_count == 2
    assert result.pinned_count == 1

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["root_count"] == 2
    assert payload["sub_count"] == 2
    assert payload["items"][0]["rpid"] == 99
    assert payload["items"][0]["is_pinned"] is True
    assert payload["items"][1]["replies"][0]["rpid"] == 101

    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "# BV1ov42117yC 评论存档" in markdown
    assert "## 1. 置顶用户（置顶）" in markdown
    assert "## 2. 根用户" in markdown
    assert "> 第二行" in markdown
    assert "（回复 @子用户）" in markdown


def test_export_video_comments_accepts_aid_and_can_skip_sub_replies(tmp_path):
    root = _comment(1)
    root["rcount"] = 0
    root["replies"] = []
    session = FakeSession({1: [root]})

    result = ReplyService(session).export_video_comments(
        aid=170001, save_dir=tmp_path, with_sub_replies=False
    )

    assert result.bvid == av2bv(170001)
    assert result.export_dir == tmp_path / av2bv(170001)
    assert result.sub_count == 0
    assert all(call[0] == CommentUrls.LIST for call in session.calls)


def test_export_video_comments_requires_identifier():
    with pytest.raises(ValueError):
        ReplyService(FakeSession({})).export_video_comments()
