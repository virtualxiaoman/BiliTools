"""MessageService 私信读取/导出单元测试（不联网）。"""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.api.errors import BiliAPIError
from src.services.message import (
    DEFAULT_MESSAGE_GROUPS,
    MESSAGE_GROUP_NAMES,
    MessageService,
    _format_count,
    _format_duration,
    _message_html_body,
    _message_link,
    _message_text,
    _sanitize_data,
    _sanitize_text,
)
from src.urls.login_urls import LoginUrls
from src.urls.message_urls import MessageUrls
from src.urls.user_urls import UserUrls

ACCOUNT_MID = 1000
PEER_MID = 2001


class FakeCookie:
    has_valid_session = True


class FakeSession:
    """按 URL/游标返回预置分页数据，并记录每次请求参数。"""

    def __init__(self, session_pages=None, message_pages=None,
                 message_errors=None, nav=None, user_names=None):
        self.session_pages = session_pages or {}
        self.message_pages = message_pages or {}
        self.message_errors = message_errors or {}
        self.user_names = user_names or {}
        self.nav = nav if nav is not None else {
            "isLogin": True, "mid": ACCOUNT_MID, "uname": "我的昵称",
        }
        self.calls = []
        self.cookie = FakeCookie()
        self.session = SimpleNamespace(headers={"User-Agent": "test"})
        self._session_cursor = {}
        self._message_cursor = {}

    def get(self, url, params=None, headers=None, **kwargs):
        params = dict(params or {})
        self.calls.append((url, params))
        if url == LoginUrls.LOGIN_STATE:
            return copy.deepcopy(self.nav)
        if url == UserUrls.CARDS:
            uids = [
                int(part) for part in str(params.get("uids", "")).split(",")
                if part.strip().isdigit()
            ]
            return [
                {
                    "mid": uid,
                    "name": self.user_names.get(uid, f"昵称{uid}"),
                    "face": "",
                    "level": 1,
                }
                for uid in uids
            ]
        if url == MessageUrls.GET_SESSIONS:
            group = params["session_type"]
            pages = self.session_pages.get(group) or []
            index = self._session_cursor.get(group, 0)
            self._session_cursor[group] = index + 1
            if index >= len(pages):
                return {"session_list": None, "has_more": 0}
            return copy.deepcopy(pages[index])
        if url == MessageUrls.FETCH_SESSION_MSGS:
            key = (params["talker_id"], params["session_type"])
            if key in self.message_errors:
                raise self.message_errors[key]
            pages = self.message_pages.get(key) or []
            index = self._message_cursor.get(key, 0)
            self._message_cursor[key] = index + 1
            if index >= len(pages):
                return {"messages": None, "has_more": 0}
            return copy.deepcopy(pages[index])
        raise AssertionError(f"unexpected url: {url}")

    def calls_to(self, url):
        return [params for called, params in self.calls if called == url]


def _session(talker_id, ts, session_type=1, system_msg_type=0, **extra):
    data = {
        "talker_id": talker_id,
        "session_type": session_type,
        "session_ts": ts,
        "max_seqno": ts,
        "system_msg_type": system_msg_type,
        "group_name": "",
        "last_msg": {},
    }
    data.update(extra)
    return data


def _session_page(items, has_more=0):
    return {"session_list": items, "has_more": has_more}


def _message(seqno, ts, sender_uid=PEER_MID, text="你好", msg_type=1,
             msg_status=0, content=None):
    if content is None:
        content = json.dumps({"content": text}, ensure_ascii=False)
    return {
        "sender_uid": sender_uid,
        "receiver_type": 1,
        "receiver_id": ACCOUNT_MID,
        "msg_type": msg_type,
        "content": content,
        "msg_seqno": seqno,
        "timestamp": ts,
        "msg_status": msg_status,
    }


def _message_page(items, has_more=0, min_seqno=None):
    return {
        "messages": items,
        "has_more": has_more,
        "min_seqno": min_seqno if min_seqno is not None else (
            min(item["msg_seqno"] for item in items) if items else 0
        ),
        "max_seqno": max((item["msg_seqno"] for item in items), default=0),
    }


def test_message_text_and_link_extraction():
    card = _message(
        1, 100, msg_type=10,
        content=json.dumps({
            "title": "奖励到账通知",
            "text": "恭喜获得奖励",
            "jump_uri": "https://example.com/reward",
        }, ensure_ascii=False),
    )
    text = _message_text(card)
    assert "奖励到账通知" in text
    assert "恭喜获得奖励" in text
    assert _message_link(card) == "https://example.com/reward"


def test_type_11_video_card_parsing():
    content = json.dumps({
        "title": "视频标题",
        "times": 125,
        "cover": "https://i0.hdslb.com/video-cover.jpg",
        "rid": 117478361399361,
        "type_": 8,
        "desc": "视频简介",
        "bvid": "BV1xx411c7mD",
        "view": 12345,
        "danmaku": 176,
        "pub_date": 1700000000,
        "attach_msg": {"id": 55537, "content": "UP主赠言"},
    }, ensure_ascii=False)
    message = _message(1, 100, msg_type=11, content=content)

    body = _message_html_body(message, {})

    assert "视频标题" in body
    assert "https://www.bilibili.com/video/BV1xx411c7mD" in body
    assert "BV号：BV1xx411c7mD" in body
    assert "播放 1.2万" in body
    assert "弹幕 176" in body
    assert "时长 02:05" in body
    assert "2023-11-15" in body
    assert "视频简介" in body
    assert "UP主赠言" in body
    assert '<img src="https://i0.hdslb.com/video-cover.jpg"' in body
    assert "[msg_type=11]" not in body


def test_type_11_empty_metadata_falls_back_to_bvid_link():
    content = json.dumps({
        "title": "",
        "times": 0,
        "cover": "",
        "rid": 0,
        "type_": 8,
        "desc": "",
        "bvid": "BV1yy411c7mE",
        "view": 0,
        "danmaku": 0,
        "pub_date": 0,
        "attach_msg": None,
    }, ensure_ascii=False)
    message = _message(1, 100, msg_type=11, content=content)

    body = _message_html_body(message, {})

    assert "视频 BV1yy411c7mE" in body
    assert "https://www.bilibili.com/video/BV1yy411c7mE" in body
    assert "BV号：BV1yy411c7mE" in body
    assert "[msg_type=11]" not in body


def test_count_and_duration_formatting():
    assert _format_count(0) == "0"
    assert _format_count(12345) == "1.2万"
    assert _format_count(123456789) == "1.2亿"
    assert _format_duration(17) == "00:17"
    assert _format_duration(125) == "02:05"
    assert _format_duration(3725) == "01:02:05"


def test_export_type_11_downloads_cover_and_renders_card(tmp_path, monkeypatch):
    downloads = []

    def fake_download(url, save_path, headers=None, overwrite=False, **kwargs):
        downloads.append((url, Path(save_path), overwrite))
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        Path(save_path).write_bytes(b"cover")
        return len(b"cover")

    monkeypatch.setattr("src.services.message.download_stream", fake_download)
    content = json.dumps({
        "title": "视频标题",
        "times": 17,
        "cover": "https://i0.hdslb.com/video-cover.jpg",
        "bvid": "BV1xx411c7mD",
        "view": 56928,
        "danmaku": 176,
        "pub_date": 1792577751,
        "attach_msg": None,
    }, ensure_ascii=False)
    session = FakeSession(message_pages={(123, 1): [
        _message_page([_message(1, 100, msg_type=11, content=content)]),
    ]})

    result = MessageService(session, default_dir=tmp_path).export_user_messages(
        123, request_interval=0
    )

    assert len(downloads) == 1
    assert downloads[0][1].exists()
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "视频标题" in markdown
    assert "https://www.bilibili.com/video/BV1xx411c7mD" in markdown
    assert '<img src="assets/' in markdown
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert len(payload["assets"]) == 1


def test_sanitize_text_handles_lone_and_paired_surrogates():
    assert _sanitize_text("前\ud83d后") == "前\ufffd后"
    assert _sanitize_text("\ud83d\ude00") == "😀"
    assert _sanitize_text("正常 😀") == "正常 😀"
    assert _sanitize_data({"x": ["a\ud83d", "\ud83d\ude00"]}) == {
        "x": ["a\ufffd", "😀"],
    }


def test_export_replaces_lone_surrogates_without_crashing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.services.message.download_stream",
        lambda *args, **kwargs: 0,
    )
    # content 是接口返回的内层 JSON 字符串；其中 \ud83d 是孤立的高位代理。
    content = '{"content": "残缺表情\\ud83d末尾"}'
    session = FakeSession(
        message_pages={(123, 1): [_message_page([_message(1, 100, content=content)])]},
        user_names={123: "对方\ud83d昵称"},
    )

    result = MessageService(session, default_dir=tmp_path).export_user_messages(
        123, request_interval=0
    )

    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "\ufffd" in markdown
    assert "\ud83d" not in markdown
    assert "对方\ufffd昵称" in markdown
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["message_count"] == 1


def test_get_user_messages_paginates_dedupes_and_sorts(tmp_path):
    pages = [
        _message_page([_message(5, 105), _message(4, 104)], has_more=1),
        _message_page([_message(4, 104), _message(3, 103), _message(2, 102)],
                      has_more=1),
        _message_page([_message(1, 101)], has_more=0),
    ]
    session = FakeSession(message_pages={(123, 1): pages})
    service = MessageService(session, default_dir=tmp_path)

    messages = service.get_user_messages(123, request_interval=0)

    assert [message["msg_seqno"] for message in messages] == [1, 2, 3, 4, 5]
    calls = session.calls_to(MessageUrls.FETCH_SESSION_MSGS)
    assert [call.get("end_seqno") for call in calls] == [None, 4, 2]
    assert all(call["mobi_app"] == "web" for call in calls)
    assert all(call["sender_device_id"] == 1 for call in calls)

    with pytest.raises(ValueError):
        service.get_user_messages(0)
    with pytest.raises(ValueError):
        service.get_user_messages(True)


def test_get_conversations_default_groups_filter_system_and_merge(tmp_path):
    session = FakeSession(session_pages={
        1: [
            _session_page([
                _session(400, 400, system_msg_type=7),
                _session(300, 300),
                _session(200, 200),
            ], has_more=1),
            _session_page([_session(100, 100)]),
        ],
        2: [_session_page([_session(250, 250)])],
        3: [_session_page([_session(50, 50, session_type=2)])],
    })
    service = MessageService(session, default_dir=tmp_path)

    sessions = service.get_conversations(request_interval=0)

    assert [item["session_ts"] for item in sessions] == [300, 250, 200, 100, 50]
    assert 400 not in {item["talker_id"] for item in sessions}
    requested_groups = [
        call["session_type"] for call in session.calls_to(MessageUrls.GET_SESSIONS)
    ]
    assert set(requested_groups) == set(DEFAULT_MESSAGE_GROUPS)
    assert set(DEFAULT_MESSAGE_GROUPS) == set(MESSAGE_GROUP_NAMES) - {7}
    type1_calls = [
        call for call in session.calls_to(MessageUrls.GET_SESSIONS)
        if call["session_type"] == 1
    ]
    assert [call.get("end_ts") for call in type1_calls] == [None, 200]


def test_get_conversations_explicit_system_group_is_included(tmp_path):
    session = FakeSession(session_pages={
        7: [_session_page([_session(400, 400, system_msg_type=7)])],
    })
    service = MessageService(session, default_dir=tmp_path)

    sessions = service.get_conversations(groups=[7], request_interval=0)

    assert [item["talker_id"] for item in sessions] == [400]
    # 实测 7 可能为空，显式请求系统消息时需要补查 1/9
    assert {call["session_type"] for call in session.calls_to(MessageUrls.GET_SESSIONS)} == {
        7, 1, 9,
    }


def test_system_only_ignores_normal_sessions_from_groups_1_and_9(tmp_path):
    session = FakeSession(session_pages={
        1: [_session_page([
            _session(500, 500),
            _session(400, 400, system_msg_type=7),
        ])],
        9: [_session_page([_session(300, 300, system_msg_type=7)])],
    })
    service = MessageService(session, default_dir=tmp_path)

    sessions = service.get_conversations(groups=[7], request_interval=0)

    assert [item["talker_id"] for item in sessions] == [400, 300]
    assert all(item["system_msg_type"] == 7 for item in sessions)


def test_group_normalization_and_validation(tmp_path):
    service = MessageService(FakeSession(), default_dir=tmp_path)

    assert service._normalize_groups(None) == DEFAULT_MESSAGE_GROUPS
    assert service._normalize_groups(["用户", "粉丝团", 3]) == (1, 3)
    assert service._normalize_groups([1, "1", 2]) == (1, 2)
    assert service._normalize_groups([]) == ()

    with pytest.raises(ValueError):
        service._normalize_groups([4])
    with pytest.raises(ValueError):
        service._normalize_groups(["不存在"])
    with pytest.raises(ValueError):
        service._normalize_groups(True)


def test_max_num_limits_conversations_and_marks_truncated(tmp_path):
    session = FakeSession(session_pages={
        1: [_session_page([_session(300, 300), _session(200, 200), _session(100, 100)])],
    })
    service = MessageService(session, default_dir=tmp_path)

    sessions, truncated = service._collect_conversations((1,), max_num=2,
                                                         request_interval=0)

    assert [item["session_ts"] for item in sessions] == [300, 200]
    assert truncated is True
    assert len(session.calls_to(MessageUrls.GET_SESSIONS)) == 1

    empty_sessions, empty_truncated = service._collect_conversations(
        (1,), max_num=0, request_interval=0
    )
    assert empty_sessions == []
    assert empty_truncated is False
    with pytest.raises(ValueError):
        service._collect_conversations((1,), max_num=-2, request_interval=0)


def test_get_all_messages_continues_after_business_error(tmp_path):
    session = FakeSession(
        session_pages={
            1: [_session_page([_session(300, 300), _session(200, 200)])],
        },
        message_pages={
            (300, 1): [_message_page([_message(1, 100)])],
        },
        message_errors={(200, 1): BiliAPIError(700013, "已解散QAQ")},
    )
    service = MessageService(session, default_dir=tmp_path)

    conversations = service.get_all_messages(groups=[1], request_interval=0)

    assert [item["talker_id"] for item in conversations] == [300, 200]
    assert conversations[0]["message_count"] == 1
    assert conversations[0]["error"] == ""
    assert conversations[1]["messages"] == []
    assert "700013" in conversations[1]["error"]


def test_export_user_messages_writes_json_and_markdown(tmp_path, monkeypatch):
    downloads = []

    def fake_download(url, save_path, headers=None, overwrite=False, **kwargs):
        downloads.append((url, Path(save_path), overwrite))
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        Path(save_path).write_bytes(b"image-bytes")
        return len(b"image-bytes")

    monkeypatch.setattr("src.services.message.download_stream", fake_download)

    content_with_newline = json.dumps({"content": "第一行\n第二行"}, ensure_ascii=False)
    image_content = json.dumps(
        {"url": "https://i0.hdslb.com/example.jpg", "width": 10, "height": 10},
        ensure_ascii=False,
    )
    session = FakeSession(message_pages={(123, 1): [
        _message_page([
            _message(1, 1700000000, sender_uid=ACCOUNT_MID, text="你好"),
            _message(2, 1700000001, text="收到", msg_type=2, content=image_content),
            _message(3, 1700000002, text="撤回内容", msg_status=1),
            _message(4, 1700000003, content=content_with_newline),
        ]),
    ]})
    service = MessageService(session, default_dir=tmp_path)

    result = service.export_user_messages(123, request_interval=0)

    expected_dir = tmp_path / str(ACCOUNT_MID) / "123"
    assert result.export_dir == expected_dir
    assert result.conversation_dirs == [expected_dir]
    assert result.talker_id == 123
    assert result.conversation_count == 1
    assert result.message_count == 4
    assert result.new_message_count == 4
    assert result.truncated is False
    assert result.json_path == expected_dir / "messages.json"
    assert result.markdown_path == expected_dir / "messages.md"
    assert result.markdown_path.exists()

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["version"] == 2
    assert payload["account_mid"] == ACCOUNT_MID
    assert payload["account_name"] == "我的昵称"
    assert payload["talker_id"] == 123
    assert payload["session_type"] == 1
    assert payload["message_count"] == 4
    assert payload["names"]["123"] == "昵称123"
    assert payload["names"]["2001"] == "昵称2001"
    assert [message["msg_seqno"] for message in payload["messages"]] == [1, 2, 3, 4]

    assert len(downloads) == 1
    assert downloads[0][0] == "https://i0.hdslb.com/example.jpg"
    assert downloads[0][1].exists()
    assert downloads[0][2] is False
    assert payload["assets"]["seqno|2:0"]["file"].startswith("assets/")

    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "# 与 用户 123 的私信记录" in markdown
    assert "- 我的 mid：1000（我的昵称）" in markdown
    assert "- 对方 mid：123（昵称123）" in markdown
    assert "background:#d6eaff" in markdown  # 我的气泡：浅蓝色
    assert "background:#d9f7be" in markdown  # 对方气泡：浅绿色
    assert "justify-content:flex-end" in markdown
    assert "justify-content:flex-start" in markdown
    assert "我的昵称 · " in markdown
    assert "昵称2001 · " in markdown
    assert "你好" in markdown
    assert '<img src="assets/' in markdown
    assert "已撤回" in markdown
    assert "第一行<br>第二行" in markdown
    assert "暂无消息" not in markdown


def test_export_user_messages_incremental_and_force(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.services.message.download_stream",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应下载图片")),
    )

    first = FakeSession(message_pages={(123, 1): [
        _message_page([_message(2, 102), _message(1, 101)]),
    ]})
    result1 = MessageService(first, default_dir=tmp_path).export_user_messages(
        123, request_interval=0
    )
    assert result1.message_count == 2
    assert result1.new_message_count == 2

    second = FakeSession(message_pages={(123, 1): [
        _message_page([
            _message(3, 103),
            _message(2, 102),
            _message(1, 101),
        ]),
    ]})
    result2 = MessageService(second, default_dir=tmp_path).export_user_messages(
        123, request_interval=0
    )
    assert result2.message_count == 3
    assert result2.new_message_count == 1
    payload2 = json.loads(result2.json_path.read_text(encoding="utf-8"))
    assert [message["msg_seqno"] for message in payload2["messages"]] == [1, 2, 3]

    third = FakeSession(message_pages={(123, 1): [
        _message_page([
            _message(3, 103),
            _message(2, 102),
            _message(1, 101),
        ]),
    ]})
    result3 = MessageService(third, default_dir=tmp_path).export_user_messages(
        123, request_interval=0
    )
    assert result3.message_count == 3
    assert result3.new_message_count == 0

    # force=True 忽略已有缓存：接口只返回 4/5 时，JSON 中不再保留 1/2/3。
    forced = FakeSession(message_pages={(123, 1): [
        _message_page([_message(5, 105), _message(4, 104)]),
    ]})
    result4 = MessageService(forced, default_dir=tmp_path).export_user_messages(
        123, request_interval=0, force=True
    )
    assert result4.forced is True
    assert result4.message_count == 2
    assert result4.new_message_count == 2
    payload4 = json.loads(result4.json_path.read_text(encoding="utf-8"))
    assert [message["msg_seqno"] for message in payload4["messages"]] == [4, 5]
    markdown4 = result4.markdown_path.read_text(encoding="utf-8")
    assert "消息数：2" in markdown4


def test_export_assets_are_cached_and_force_redownloads(tmp_path, monkeypatch):
    downloads = []

    def fake_download(url, save_path, headers=None, overwrite=False, **kwargs):
        downloads.append((url, Path(save_path), overwrite))
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        Path(save_path).write_bytes(b"image-bytes")
        return len(b"image-bytes")

    monkeypatch.setattr("src.services.message.download_stream", fake_download)
    image_content = json.dumps({"url": "https://i0.hdslb.com/pic.png"})
    session_data = {(123, 1): [_message_page([
        _message(1, 100, msg_type=2, content=image_content),
    ])]}

    service = MessageService(FakeSession(message_pages=session_data),
                             default_dir=tmp_path)
    result1 = service.export_user_messages(123, request_interval=0)
    assert len(downloads) == 1
    asset_file = next((result1.export_dir / "assets").iterdir())
    assert asset_file.exists()

    service2 = MessageService(FakeSession(message_pages=session_data),
                              default_dir=tmp_path)
    result2 = service2.export_user_messages(123, request_interval=0)
    assert result2.message_count == 1
    assert len(downloads) == 1  # 已有资源映射且文件存在，不重复下载

    service3 = MessageService(FakeSession(message_pages=session_data),
                              default_dir=tmp_path)
    service3.export_user_messages(123, request_interval=0, force=True)
    assert len(downloads) == 2
    assert downloads[-1][2] is True  # force=True 时覆盖下载

    assert result1.markdown_path.read_text(encoding="utf-8").count('<img src="assets/') == 1


def test_export_all_messages_writes_per_friend_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.services.message.download_stream",
        lambda *args, **kwargs: 0,
    )
    session = FakeSession(
        session_pages={
            1: [_session_page([_session(300, 300), _session(200, 200), _session(100, 100)])],
            2: [_session_page([_session(250, 250)])],
        },
        message_pages={
            (300, 1): [_message_page([_message(1, 100)])],
            (250, 1): [_message_page([_message(1, 100)])],
            (200, 1): [_message_page([_message(1, 100)])],
        },
    )
    service = MessageService(session, default_dir=tmp_path)

    result = service.export_all_messages(
        groups=[1, 2], max_num=2, request_interval=0, display_progress=False
    )

    account_dir = tmp_path / str(ACCOUNT_MID)
    assert result.talker_id is None
    assert result.truncated is True
    assert result.conversation_count == 2
    assert result.message_count == 2
    assert result.new_message_count == 2
    assert result.errors == []
    assert result.export_dir == account_dir
    assert result.json_path is None
    assert result.markdown_path is None
    assert result.conversation_dirs == [account_dir / "300", account_dir / "250"]
    assert not (account_dir / "all").exists()

    for friend_mid in ("300", "250"):
        friend_dir = account_dir / friend_mid
        payload = json.loads((friend_dir / "messages.json").read_text(encoding="utf-8"))
        assert payload["account_mid"] == ACCOUNT_MID
        assert payload["talker_id"] == int(friend_mid)
        assert payload["message_count"] == 1
        markdown = (friend_dir / "messages.md").read_text(encoding="utf-8")
        assert f"# 与 用户 {friend_mid} 的私信记录" in markdown

    assert not (account_dir / "200").exists()
    fetched_talkers = [
        call["talker_id"] for call in session.calls_to(MessageUrls.FETCH_SESSION_MSGS)
    ]
    assert fetched_talkers == [300, 250]


def test_export_user_messages_ignores_corrupt_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.services.message.download_stream",
        lambda *args, **kwargs: 0,
    )
    friend_dir = tmp_path / str(ACCOUNT_MID) / "123"
    friend_dir.mkdir(parents=True)
    (friend_dir / "messages.json").write_text("{bad json", encoding="utf-8")
    session = FakeSession(message_pages={(123, 1): [
        _message_page([_message(1, 100)]),
    ]})

    result = MessageService(session, default_dir=tmp_path).export_user_messages(
        123, request_interval=0
    )

    assert result.message_count == 1
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["message_count"] == 1


class _FakeProgress:
    def __init__(self):
        self.updates = []
        self.finished = 0

    def update(self, exported, message_count, failed=0):
        self.updates.append((exported, message_count, failed))

    def finish(self):
        self.finished += 1


def test_export_all_progress_object_and_callback(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.services.message.download_stream",
        lambda *args, **kwargs: 0,
    )
    session = FakeSession(
        session_pages={
            1: [_session_page([_session(300, 300), _session(200, 200)])],
        },
        message_pages={
            (300, 1): [_message_page([_message(1, 100)])],
            (200, 1): [_message_page([_message(1, 100)])],
        },
    )
    progress = _FakeProgress()
    events = []
    service = MessageService(session, default_dir=tmp_path)

    result = service.export_all_messages(
        groups=[1],
        request_interval=0,
        progress=progress,
        progress_cb=lambda exported, total, messages, failed: events.append(
            (exported, total, messages, failed)
        ),
        display_progress=False,
    )

    assert result.conversation_count == 2
    assert progress.updates == [(0, 0, 0), (1, 1, 0), (2, 2, 0)]
    assert progress.finished == 1
    assert events == [(1, 2, 1, 0), (2, 2, 2, 0)]


def test_export_all_progress_reports_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.services.message.download_stream",
        lambda *args, **kwargs: 0,
    )
    session = FakeSession(
        session_pages={
            1: [_session_page([_session(300, 300), _session(200, 200)])],
        },
        message_pages={
            (300, 1): [_message_page([_message(1, 100)])],
        },
        message_errors={(200, 1): BiliAPIError(700013, "已解散QAQ")},
    )
    progress = _FakeProgress()
    service = MessageService(session, default_dir=tmp_path)

    result = service.export_all_messages(
        groups=[1],
        request_interval=0,
        progress=progress,
        display_progress=False,
    )

    assert result.conversation_count == 1
    assert result.message_count == 1
    assert len(result.errors) == 1
    assert progress.updates == [(0, 0, 0), (1, 1, 0), (1, 1, 1)]
    assert progress.finished == 1


def test_export_all_default_progress_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "src.services.message.download_stream",
        lambda *args, **kwargs: 0,
    )
    session = FakeSession(
        session_pages={1: [_session_page([_session(300, 300)])]},
        message_pages={(300, 1): [_message_page([_message(1, 100)])]},
    )
    service = MessageService(session, default_dir=tmp_path)

    service.export_all_messages(groups=[1], max_num=1, request_interval=0)

    output = capsys.readouterr().out
    assert "已导出 0 个会话 / 共 1 个会话 / 0 条消息" in output
    assert "已导出 1 个会话 / 共 1 个会话 / 1 条消息" in output
    assert output.rstrip().endswith("1 条消息")


def test_export_messages_dispatch_and_parameter_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.services.message.download_stream",
        lambda *args, **kwargs: 0,
    )
    session = FakeSession(
        session_pages={1: [_session_page([_session(300, 300)])]},
        message_pages={(300, 1): [_message_page([_message(1, 100)])]},
    )
    service = MessageService(session, default_dir=tmp_path)

    all_result = service.export_messages(
        mid=None, groups=[1], max_num=0, request_interval=0, display_progress=False
    )
    assert all_result.conversation_count == 0
    assert all_result.message_count == 0
    assert all_result.new_message_count == 0
    assert all_result.truncated is False
    assert all_result.export_dir == tmp_path / str(ACCOUNT_MID)
    assert all_result.json_path is None

    user_result = service.export_messages(
        mid=300, request_interval=0, force=True
    )
    assert user_result.talker_id == 300
    assert user_result.forced is True
    user_payload = json.loads(user_result.json_path.read_text(encoding="utf-8"))
    assert user_payload["talker_id"] == 300

    with pytest.raises(ValueError):
        service.export_messages(mid=-1, request_interval=0)
    with pytest.raises(ValueError):
        service.export_all_messages(groups=[4], request_interval=0)
