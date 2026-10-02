"""UP 主动态批量下载测试（mock feed + 假下载器，不联网）。"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.services.dynamic as dynamic_module
from src.api.errors import BiliAPIError, BiliRiskError
from src.services.dynamic import DynamicService
from src.urls.comment_urls import CommentUrls
from src.urls.dynamic_urls import DynamicUrls
from src.util.progress import BatchProgress, ParallelBatchProgress

FIXTURES = Path(__file__).parent / "fixtures" / "dynamic"

MID = 3493133776062465  # word 模板作者


def load_item(name: str) -> dict:
    path = FIXTURES / (name if name.endswith(".json") else f"{name}.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "item" in data:
        data = data["item"]
    return data


def ts_of(year: int, month: int, day: int, hour: int = 10) -> int:
    moment = datetime(year, month, day, hour, tzinfo=timezone(timedelta(hours=8)))
    return int(moment.timestamp())


def make_item(template: str, dyn_id: int, pub_ts: int, *, pinned: bool = False) -> dict:
    item = json.loads(json.dumps(load_item(template)))
    item["id_str"] = str(dyn_id)
    modules = item["modules"]
    modules.pop("module_tag", None)  # 模板可能自带置顶标记，避免污染测试
    modules["module_author"]["pub_ts"] = pub_ts
    if pinned:
        modules["module_tag"] = {"text": "置顶"}
    basic = item.setdefault("basic", {})
    basic["comment_id_str"] = str(dyn_id)
    basic["comment_type"] = 17
    return item


class FakeFeedSession:
    """按 offset 参数返回对应页面（无状态，可重复调用），并记录请求参数。"""

    def __init__(self, pages: list[list[dict]]):
        self.pages = pages
        self.calls: list[dict] = []
        self.session = SimpleNamespace(headers={"User-Agent": "test"})

    def get(self, url, params=None, headers=None):
        assert url == DynamicUrls.SPACE_FEED, f"unexpected url: {url}"
        params = dict(params or {})
        self.calls.append(params)
        offset = str(params.get("offset") or "")
        index = int(offset[3:]) if offset.startswith("off") else 0
        page = self.pages[index] if index < len(self.pages) else []
        has_more = index + 1 < len(self.pages)
        return {
            "items": page,
            "offset": f"off{index + 1}" if has_more else "",
            "has_more": has_more,
        }


class RiskFeedSession(FakeFeedSession):
    """前 risk_times 次请求抛风控错误（-412），之后正常返回。"""

    def __init__(self, pages: list[list[dict]], risk_times: int = 1):
        super().__init__(pages)
        self.risk_times = risk_times
        self.risk_failures = 0

    def get(self, url, params=None, headers=None):
        if self.risk_failures < self.risk_times:
            self.risk_failures += 1
            self.calls.append(dict(params or {}))
            raise BiliRiskError("模拟风控 -412")
        return super().get(url, params=params, headers=headers)


class CaptchaFeedSession(FakeFeedSession):
    """前 captcha_times 次请求抛 -352（BiliAPIError），之后正常返回。"""

    def __init__(self, pages: list[list[dict]], captcha_times: int = 1):
        super().__init__(pages)
        self.captcha_times = captcha_times
        self.captcha_failures = 0

    def get(self, url, params=None, headers=None):
        if self.captcha_failures < self.captcha_times:
            self.captcha_failures += 1
            self.calls.append(dict(params or {}))
            raise BiliAPIError(-352, "-352")
        return super().get(url, params=params, headers=headers)


class FlakyFeedSession(FakeFeedSession):
    """第 fail_at 次请求抛 -352（其余正常），用于中断保存场景。"""

    def __init__(self, pages: list[list[dict]], fail_at: int = 2):
        super().__init__(pages)
        self.fail_at = fail_at
        self.request_count = 0

    def get(self, url, params=None, headers=None):
        self.request_count += 1
        if self.request_count >= self.fail_at:
            self.calls.append(dict(params or {}))
            raise BiliAPIError(-352, "-352")
        return super().get(url, params=params, headers=headers)


class MappingFeedSession:
    """按显式 offset→items 映射返回页面（增量刷新/跳页场景）。

    返回的 next offset 为页内最后一条的 id，因此映射键应为"上一页最后一条动态 id"。
    """

    def __init__(self, mapping: dict):
        self.mapping = mapping
        self.calls: list = []
        self.session = SimpleNamespace(headers={"User-Agent": "test"})

    def get(self, url, params=None, headers=None):
        assert url == DynamicUrls.SPACE_FEED, f"unexpected url: {url}"
        params = dict(params or {})
        self.calls.append(params)
        offset = str(params.get("offset") or "")
        items = self.mapping.get(offset, [])
        next_offset = str(items[-1]["id_str"]) if items else ""
        has_more = bool(next_offset) and next_offset in self.mapping
        return {"items": items, "offset": next_offset if has_more else "", "has_more": has_more}


class FakeReply:
    def __init__(self):
        self.calls: list = []

    def get_comments_by_oid(self, oid, comment_type, sort="latest", max_count=-1, page_size=20):
        self.calls.append((oid, comment_type, sort, max_count))
        return []


class WorkerSession:
    """多账号 worker 的会话桩：只处理评论列表请求，统计各账号被调用的次数。"""

    def __init__(self, name: str):
        self.name = name
        self.comment_calls = 0
        self.session = SimpleNamespace(headers={"User-Agent": "test"})

    def get(self, url, params=None, headers=None):
        if url == CommentUrls.LIST:
            self.comment_calls += 1
            return {"replies": []}
        raise AssertionError(f"unexpected url: {url}")


@pytest.fixture
def wbi_stub(monkeypatch):
    """注入 WBI 参数并禁用真实等待（爬取节流在单元测试里不阻塞）。"""
    monkeypatch.setattr(
        dynamic_module, "get_wbi",
        lambda params: params.update({"wts": 1, "w_rid": "sig"}),
    )
    monkeypatch.setattr(dynamic_module.time, "sleep", lambda seconds: None)


@pytest.fixture
def sleep_recorder(monkeypatch):
    """记录 sleep 时长（验证页间隔与风控退避），不真实等待。"""
    sleeps: list[float] = []
    monkeypatch.setattr(
        dynamic_module, "get_wbi",
        lambda params: params.update({"wts": 1, "w_rid": "sig"}),
    )
    monkeypatch.setattr(dynamic_module.time, "sleep", lambda seconds: sleeps.append(seconds))
    return sleeps


@pytest.fixture
def download_stub(monkeypatch):
    """替换 download_stream：写假字节；fail_markers 中的标记命中任意镜像变体即失败。"""
    state = {"calls": [], "fail_markers": set()}

    def fake_download(url, path, headers=None, **kwargs):
        state["calls"].append(url)
        if any(marker in url for marker in state["fail_markers"]):
            raise IOError("模拟下载失败")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"data")
        callback = kwargs.get("progress_cb")
        if callback is not None:
            callback(4, 4)
        return 4

    monkeypatch.setattr("src.services.dynamic.download_stream", fake_download)
    return state


def make_service(tmp_path, pages):
    session = FakeFeedSession(pages)
    service = DynamicService(session=session, default_dir=tmp_path)
    service.reply_service = FakeReply()
    return service, session


class TestListUserDynamics:
    def test_paginates_dedupes_and_passes_offset(self, tmp_path, wbi_stub):
        pinned_old = make_item("word", 900001, ts_of(2024, 1, 1), pinned=True)
        newest = make_item("word", 900002, ts_of(2026, 9, 22, 20))
        middle = make_item("word", 900003, ts_of(2026, 9, 22, 10))
        oldest = make_item("word", 900004, ts_of(2026, 9, 21, 10))
        service, session = make_service(tmp_path, [[pinned_old, newest, middle], [pinned_old, oldest]])

        items = service.list_user_dynamics(MID)

        assert [item["id_str"] for item in items] == ["900001", "900002", "900003", "900004"]
        assert len(session.calls) == 2
        assert session.calls[0]["host_mid"] == MID
        assert "offset" not in session.calls[0]
        assert session.calls[1]["offset"] == "off1"
        assert session.calls[0]["wts"] == 1  # WBI 参数已注入

    def test_max_count_stops_early(self, tmp_path, wbi_stub):
        page = [make_item("word", 900001 + i, ts_of(2026, 9, 20, 20 - i)) for i in range(3)]
        service, session = make_service(tmp_path, [page, [make_item("word", 900010, ts_of(2026, 9, 19))]])

        items = service.list_user_dynamics(MID, max_count=2)

        assert len(items) == 2
        assert len(session.calls) == 1  # 达到上限后不再翻页

    def test_since_filters_and_stops(self, tmp_path, wbi_stub):
        fresh = make_item("word", 900001, ts_of(2026, 9, 22, 10))
        stale = make_item("word", 900002, ts_of(2026, 9, 18, 10))
        service, session = make_service(
            tmp_path, [[fresh, stale], [make_item("word", 900003, ts_of(2026, 9, 17))]]
        )

        items = service.list_user_dynamics(MID, since="2026-09-21")

        assert [item["id_str"] for item in items] == ["900001"]
        assert len(session.calls) == 1  # 出现早于 since 的动态后提前停止

    def test_pinned_old_item_filtered_by_since(self, tmp_path, wbi_stub):
        pinned_old = make_item("word", 900001, ts_of(2024, 1, 1), pinned=True)
        fresh = make_item("word", 900002, ts_of(2026, 9, 22, 10))
        service, _ = make_service(tmp_path, [[pinned_old, fresh]])

        items = service.list_user_dynamics(MID, since="2026-09-01")

        assert [item["id_str"] for item in items] == ["900002"]

    def test_page_interval_pacing_with_jitter(self, tmp_path, sleep_recorder):
        """页间隔 = 基准 + 最多 50% 随机抖动；第一页不等待。"""
        pages = [
            [make_item("word", 900001, ts_of(2026, 9, 20, 20))],
            [make_item("word", 900002, ts_of(2026, 9, 19, 20))],
            [make_item("word", 900003, ts_of(2026, 9, 18, 20))],
        ]
        service, session = make_service(tmp_path, pages)

        items = service.list_user_dynamics(MID, page_interval=0.2, display=False)

        assert len(items) == 3
        assert len(session.calls) == 3
        assert len(sleep_recorder) == 2  # 翻页两次 → 等待两次
        assert all(0.2 <= seconds <= 0.3 for seconds in sleep_recorder)

    def test_zero_interval_skips_waiting(self, tmp_path, sleep_recorder):
        service, _ = make_service(tmp_path, [[make_item("word", 900001, ts_of(2026, 9, 20))]])
        service.list_user_dynamics(MID, page_interval=0, display=False)
        assert sleep_recorder == []

    def test_crawl_progress_callback(self, tmp_path, wbi_stub):
        pages = [
            [make_item("word", 900001, ts_of(2026, 9, 20, 20)), make_item("word", 900002, ts_of(2026, 9, 19, 20))],
            [make_item("word", 900003, ts_of(2026, 9, 18, 20))],
        ]
        service, _ = make_service(tmp_path, pages)

        events = []
        items = service.list_user_dynamics(MID, progress_cb=lambda page, count: events.append((page, count)))

        assert events == [(1, 2), (2, 3)]
        assert len(items) == 3

    def test_crawl_display_prints_progress(self, tmp_path, wbi_stub, capsys):
        pages = [
            [make_item("word", 900001, ts_of(2026, 9, 20))],
            [make_item("word", 900002, ts_of(2026, 9, 19))],
        ]
        service, _ = make_service(tmp_path, pages)

        service.list_user_dynamics(MID)

        out = capsys.readouterr().out
        assert "第 1 页，累计 1 条，当前最新一条爬取的动态日期：2026-09-20，动态id：900001" in out
        assert "第 2 页，累计 2 条，当前最新一条爬取的动态日期：2026-09-19，动态id：900002" in out
        assert "完成：共 2 条" in out

    def test_risk_retries_with_backoff(self, tmp_path, sleep_recorder):
        """单页触发 -412 时指数退避重试；成功后继续。"""
        session = RiskFeedSession([[make_item("word", 900001, ts_of(2026, 9, 20))]], risk_times=1)
        service = DynamicService(session=session, default_dir=tmp_path)
        service.reply_service = FakeReply()

        items = service.list_user_dynamics(MID, page_interval=0, display=False)

        assert len(items) == 1
        assert session.risk_failures == 1
        assert len(session.calls) == 2  # 风控一次 + 重试成功一次
        assert any(seconds >= 30 for seconds in sleep_recorder)  # 30s 起步的退避

    def test_risk_raises_after_retries_exhausted(self, tmp_path, sleep_recorder):
        session = RiskFeedSession([[make_item("word", 900001, ts_of(2026, 9, 20))]], risk_times=99)
        service = DynamicService(session=session, default_dir=tmp_path)
        service.reply_service = FakeReply()

        with pytest.raises(BiliRiskError):
            service.list_user_dynamics(MID, page_interval=0, display=False, risk_retries=1)

        assert session.risk_failures == 2  # 首次 + 1 次重试


class TestNormalizeMid:
    @pytest.mark.parametrize("value,expected", [(123, 123), ("36081646", 36081646), ("  123  ", 123)])
    def test_accepts(self, value, expected):
        assert DynamicService.normalize_mid(value) == expected

    @pytest.mark.parametrize("bad", [None, True, "", "abc", "12.3", 0, -5, "https://space.bilibili.com/1"])
    def test_rejects(self, bad):
        with pytest.raises(ValueError):
            DynamicService.normalize_mid(bad)


class TestDownloadUserDynamics:
    def test_same_day_numbering_follows_publication_order(self, tmp_path, wbi_stub, download_stub):
        later = make_item("word", 900002, ts_of(2026, 9, 20, 20))
        earlier = make_item("word", 900001, ts_of(2026, 9, 20, 10))
        service, session = make_service(tmp_path, [[later, earlier]])  # feed 时间倒序
        progress_events = []

        results = service.download_user_dynamics(
            MID, with_comments=False,
            progress=BatchProgress(n=1, label="test", display=False),
            progress_cb=lambda done, total: progress_events.append((done, total)),
        )

        assert [result.path.name for result in results] == ["2026-09-20_1", "2026-09-20_2"]
        assert (results[0].path / "dynamic_id.txt").read_text(encoding="utf-8").strip() == "900001"
        assert (results[1].path / "dynamic_id.txt").read_text(encoding="utf-8").strip() == "900002"
        assert progress_events == [(1, 2), (2, 2)]
        assert (tmp_path / str(MID) / "dynamic_list.json").is_file()  # 全量爬取已保存快照

        # 二次运行：读取快照做增量刷新（仅爬 1 页确认无新动态），媒体全部命中缓存
        download_stub["calls"].clear()
        feed_calls_before = len(session.calls)
        again = service.download_user_dynamics(
            MID, with_comments=False,
            progress=BatchProgress(n=1, label="test", display=False),
        )
        assert all(result.cached for result in again)
        assert download_stub["calls"] == []
        assert len(session.calls) == feed_calls_before + 1  # 撞到缓存重叠即停

        forced = service.download_user_dynamics(
            MID, force=True, with_comments=False,
            progress=BatchProgress(n=1, label="test", display=False),
        )
        assert not any(result.cached for result in forced)
        assert len(download_stub["calls"]) > 0
        assert (results[0].path / "dynamic_id.txt").is_file()

    def test_partial_failure_marks_only_that_dynamic(self, tmp_path, wbi_stub, download_stub):
        broken = make_item("draw_lottery", 900001, ts_of(2026, 9, 20, 10))
        broken["modules"]["module_dynamic"]["major"]["opus"]["pics"][0]["url"] += "?broken"
        healthy = make_item("word", 900002, ts_of(2026, 9, 21, 10))
        download_stub["fail_markers"].add("?broken")  # 镜像变体同样命中
        service, _ = make_service(tmp_path, [[healthy, broken]])

        results = service.download_user_dynamics(
            MID, with_comments=False,
            progress=BatchProgress(n=1, label="test", display=False),
        )

        by_id = {result.path.name: result for result in results}
        broken_result = by_id["2026-09-20_1"]
        healthy_result = by_id["2026-09-21_1"]
        assert broken_result.failures
        assert (broken_result.path / "dynamic_id_failed.txt").is_file()
        assert not (broken_result.path / "dynamic_id.txt").exists()
        assert not healthy_result.failures
        assert (healthy_result.path / "dynamic_id.txt").is_file()

    def test_empty_feed_returns_empty(self, tmp_path, wbi_stub, download_stub):
        service, _ = make_service(tmp_path, [[]])
        assert service.download_user_dynamics(MID) == []

    def test_batch_quiets_nested_media_progress(self, tmp_path, wbi_stub, download_stub, monkeypatch):
        """批量模式下：主动态与转发递归的媒体进度都应静默（display=False）。"""
        displays: list[bool] = []
        real_progress = dynamic_module.BatchProgress

        class RecordingProgress(real_progress):
            def __init__(self, *args, **kwargs):
                displays.append(bool(kwargs.get("display", True)))
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(dynamic_module, "BatchProgress", RecordingProgress)

        forward = make_item("forward", 900001, ts_of(2026, 9, 21, 10))
        service, _ = make_service(tmp_path, [[forward]])
        service.download_user_dynamics(
            MID, with_comments=False,
            progress=RecordingProgress(n=1, label="t", display=False),
        )

        assert len(displays) >= 3  # 批量对象 + 主动态媒体 + 转发原动态媒体
        assert all(display is False for display in displays)

    def test_rejects_invalid_options(self, tmp_path, wbi_stub, download_stub):
        service, _ = make_service(tmp_path, [[]])
        with pytest.raises(ValueError):
            service.download_user_dynamics(MID, max_count=-2)
        with pytest.raises(ValueError):
            service.download_user_dynamics(MID, since="2026/09/01")
        with pytest.raises(ValueError):
            service.download_user_dynamics(MID, threads=0)


class TestAccountDistribution:
    def test_round_robin_across_accounts(self, tmp_path, wbi_stub, download_stub):
        """批量任务按下标轮询各账号：评论等 API 请求分摊到多个账号。"""
        pages = [[
            make_item("word", 900001, ts_of(2026, 9, 18, 10)),
            make_item("word", 900002, ts_of(2026, 9, 19, 10)),
            make_item("word", 900003, ts_of(2026, 9, 20, 10)),
            make_item("word", 900004, ts_of(2026, 9, 21, 10)),
        ]]
        feed = FakeFeedSession(pages)
        account_a, account_b = WorkerSession("a"), WorkerSession("b")
        service = DynamicService(session=feed, default_dir=tmp_path)

        results = service.download_user_dynamics(
            900000,
            account_sessions=[account_a, account_b],
            progress=BatchProgress(n=1, label="t", display=False),
        )

        assert len(results) == 4
        assert all(not result.failures for result in results)
        # 升序处理后按下标轮询：0、2 → 账号 A；1、3 → 账号 B
        assert account_a.comment_calls == 2
        assert account_b.comment_calls == 2

    def test_threads_preserve_same_day_numbering(self, tmp_path, wbi_stub, download_stub):
        """并发下载时目录先按升序预分配：同一天编号仍等于发布序。"""
        pages = [[
            make_item("word", 900003, ts_of(2026, 9, 20, 20)),
            make_item("word", 900002, ts_of(2026, 9, 20, 12)),
            make_item("word", 900001, ts_of(2026, 9, 20, 10)),
        ]]
        service, _ = make_service(tmp_path, pages)

        results = service.download_user_dynamics(
            MID, threads=2, with_comments=False,
            progress=ParallelBatchProgress(n=1, label="t", display=False),
        )

        names = {
            result.path.name: (result.path / "dynamic_id.txt").read_text(encoding="utf-8").strip()
            for result in results
        }
        assert names == {
            "2026-09-20_1": "900001",
            "2026-09-20_2": "900002",
            "2026-09-20_3": "900003",
        }
        assert [result.path.name for result in results] == [
            "2026-09-20_1", "2026-09-20_2", "2026-09-20_3",
        ]


class TestCaptchaHandling:
    def test_captcha_continue_with_handler(self, tmp_path, wbi_stub):
        """-352 暂停：自定义回调返回 True 后重试本页并继续。"""
        item = make_item("word", 900001, ts_of(2026, 9, 20))
        session = CaptchaFeedSession([[item]], captcha_times=1)
        service = DynamicService(session=session, default_dir=tmp_path)
        prompts: list = []

        items = service.list_user_dynamics(
            MID, captcha_handler=lambda message: prompts.append(message) or True, display=False,
        )

        assert len(items) == 1
        assert session.captcha_failures == 1
        assert len(session.calls) == 2  # -352 一次 + 重试成功一次
        assert len(prompts) == 1 and "验证" in prompts[0]

    def test_captcha_declined_raises(self, tmp_path, wbi_stub):
        item = make_item("word", 900001, ts_of(2026, 9, 20))
        session = CaptchaFeedSession([[item]], captcha_times=99)
        service = DynamicService(session=session, default_dir=tmp_path)

        with pytest.raises(BiliAPIError) as error:
            service.list_user_dynamics(MID, captcha_handler=lambda message: False, display=False)

        assert error.value.code == -352
        assert session.captcha_failures == 1

    def test_captcha_wait_disabled_raises(self, tmp_path, wbi_stub):
        item = make_item("word", 900001, ts_of(2026, 9, 20))
        session = CaptchaFeedSession([[item]], captcha_times=1)
        service = DynamicService(session=session, default_dir=tmp_path)

        with pytest.raises(BiliAPIError):
            service.list_user_dynamics(MID, captcha_wait=False, display=False)

    def test_interactive_console_prompt(self, tmp_path, wbi_stub, monkeypatch, capsys):
        """默认走控制台提示：输入 y 后继续。"""
        item = make_item("word", 900001, ts_of(2026, 9, 20))
        session = CaptchaFeedSession([[item]], captcha_times=1)
        service = DynamicService(session=session, default_dir=tmp_path)
        monkeypatch.setattr("builtins.input", lambda prompt="": "y")

        items = service.list_user_dynamics(MID)

        assert len(items) == 1
        out = capsys.readouterr().out
        assert "验证" in out


class TestListSnapshot:
    def _snapshot_path(self, tmp_path) -> Path:
        return tmp_path / str(MID) / "dynamic_list.json"

    def test_full_crawl_saves_snapshot_and_loads(self, tmp_path, wbi_stub):
        pages = [[
            make_item("word", 900002, ts_of(2026, 9, 21)),
            make_item("word", 900001, ts_of(2026, 9, 20)),
        ]]
        service, _ = make_service(tmp_path, pages)

        items = service.list_user_dynamics(MID)

        assert [item["id_str"] for item in items] == ["900002", "900001"]
        path = self._snapshot_path(tmp_path)
        assert path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["complete"] is True and payload["count"] == 2
        loaded = service.load_dynamic_list(MID, save_dir=tmp_path)
        assert [item["id_str"] for item in loaded] == ["900002", "900001"]

    def test_incremental_refresh_skips_cached_middle(self, tmp_path, wbi_stub):
        """快照完整时：爬到与快照重叠即停，只补最新的一头。"""
        pages = [[make_item("word", 900002, ts_of(2026, 9, 21)), make_item("word", 900001, ts_of(2026, 9, 20))]]
        service, _ = make_service(tmp_path, pages)
        service.list_user_dynamics(MID)

        # 空间出现新动态 900003；首页 = [新动态, 缓存中的 900002]
        session2 = FakeFeedSession([[
            make_item("word", 900003, ts_of(2026, 9, 22)),
            make_item("word", 900002, ts_of(2026, 9, 21)),
        ]])
        service2 = DynamicService(session=session2, default_dir=tmp_path)

        items = service2.list_user_dynamics(MID, display=False)

        assert [item["id_str"] for item in items] == ["900003", "900002", "900001"]
        assert len(session2.calls) == 1  # 撞到缓存重叠即停，未重爬中段
        payload = json.loads(self._snapshot_path(tmp_path).read_text(encoding="utf-8"))
        assert payload["count"] == 3 and payload["complete"] is True

    def test_incomplete_snapshot_continues_deeper(self, tmp_path, wbi_stub):
        """快照未爬完时：跳到快照最旧一条之后，继续向更早翻页。"""
        service, _ = make_service(tmp_path, [[]])
        cached = [
            make_item("word", 900010, ts_of(2026, 9, 10)),
            make_item("word", 900009, ts_of(2026, 9, 9)),
        ]
        service._save_dynamic_list(MID, cached, save_dir=tmp_path, complete=False, display=False)

        mapping = {
            "": [make_item("word", 900011, ts_of(2026, 9, 11)), make_item("word", 900010, ts_of(2026, 9, 10))],
            "900009": [make_item("word", 900008, ts_of(2026, 9, 8)), make_item("word", 900007, ts_of(2026, 9, 7))],
        }
        session = MappingFeedSession(mapping)
        service2 = DynamicService(session=session, default_dir=tmp_path)

        items = service2.list_user_dynamics(MID, display=False)

        assert [item["id_str"] for item in items] == ["900011", "900010", "900009", "900008", "900007"]
        assert len(session.calls) == 2
        assert session.calls[1]["offset"] == "900009"  # 以快照最旧一条为 offset 跳页
        payload = json.loads(self._snapshot_path(tmp_path).read_text(encoding="utf-8"))
        assert payload["count"] == 5 and payload["complete"] is True

    def test_use_cache_false_full_recrawl(self, tmp_path, wbi_stub):
        pages = [[make_item("word", 900002, ts_of(2026, 9, 21)), make_item("word", 900001, ts_of(2026, 9, 20))]]
        service, _ = make_service(tmp_path, pages)
        service.list_user_dynamics(MID)

        session2 = FakeFeedSession(pages)
        service2 = DynamicService(session=session2, default_dir=tmp_path)
        items = service2.list_user_dynamics(MID, use_cache=False, display=False)

        assert len(items) == 2
        assert len(session2.calls) == 1  # 完整重爬（未读快照）

    def test_abort_saves_partial_incomplete_snapshot(self, tmp_path, wbi_stub):
        """中途 -352 放弃时：保存已获取的部分（标记未完成）。"""
        pages = [[make_item("word", 900001, ts_of(2026, 9, 20))], [make_item("word", 900000, ts_of(2026, 9, 19))]]
        session = FlakyFeedSession(pages, fail_at=2)
        service = DynamicService(session=session, default_dir=tmp_path)

        with pytest.raises(BiliAPIError):
            service.list_user_dynamics(MID, captcha_handler=lambda message: False, display=False)

        payload = json.loads(self._snapshot_path(tmp_path).read_text(encoding="utf-8"))
        assert payload["complete"] is False
        assert [item["id_str"] for item in payload["items"]] == ["900001"]

    def test_filtered_request_skips_snapshot(self, tmp_path, wbi_stub):
        """带 max_count 的请求不读写快照，避免污染完整列表。"""
        pages = [[make_item("word", 900002, ts_of(2026, 9, 21)), make_item("word", 900001, ts_of(2026, 9, 20))]]
        service, _ = make_service(tmp_path, pages)

        items = service.list_user_dynamics(MID, max_count=1, display=False)

        assert [item["id_str"] for item in items] == ["900002"]
        assert not self._snapshot_path(tmp_path).exists()
