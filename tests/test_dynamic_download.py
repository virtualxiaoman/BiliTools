"""动态下载流程测试（mock session + 假下载器，不联网）。"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services.dynamic import DynamicService, _mirror_urls
from src.urls.dynamic_urls import DynamicUrls
from src.util.progress import BatchProgress

FIXTURES = Path(__file__).parent / "fixtures" / "dynamic"


def load_item(name: str) -> dict:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "item" in data:
        data = data["item"]
    return data


def load_data(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeSession:
    def __init__(self, item: dict, opus_data: dict | None = None):
        self.item = item
        self.opus_data = opus_data
        self.detail_calls = 0
        self.opus_calls = 0
        self.session = SimpleNamespace(headers={"User-Agent": "test"})

    def get(self, url, params=None, headers=None):
        if url == DynamicUrls.DETAIL:
            assert params["features"] == DynamicUrls.DETAIL_FEATURES
            self.detail_calls += 1
            return {"item": self.item}
        if url == DynamicUrls.OPUS_DETAIL:
            self.opus_calls += 1
            assert self.opus_data is not None
            return self.opus_data
        raise AssertionError(f"unexpected url: {url}")


class FakeReply:
    def __init__(self, items=None, error: Exception | None = None):
        self.items = items or []
        self.error = error
        self.calls: list = []

    def get_comments_by_oid(self, oid, comment_type, sort="latest", max_count=-1, page_size=20):
        self.calls.append((oid, comment_type, sort, max_count))
        if self.error is not None:
            raise self.error
        return self.items


class TestCdnMirrorFallback:
    """CDN 镜像回退顺序：原 host 优先，其次 i2、i1（不使用 i3+）。"""

    def test_mirror_order(self):
        assert _mirror_urls("https://i0.hdslb.com/bfs/x.jpg") == [
            "https://i0.hdslb.com/bfs/x.jpg",
            "https://i2.hdslb.com/bfs/x.jpg",
            "https://i1.hdslb.com/bfs/x.jpg",
        ]
        assert _mirror_urls("https://i1.hdslb.com/bfs/x.jpg") == [
            "https://i1.hdslb.com/bfs/x.jpg",
            "https://i2.hdslb.com/bfs/x.jpg",
        ]

    def test_non_mirror_hosts_pass_through(self):
        assert _mirror_urls("https://i3.hdslb.com/bfs/x.jpg") == ["https://i3.hdslb.com/bfs/x.jpg"]
        assert _mirror_urls("https://example.com/x.jpg") == ["https://example.com/x.jpg"]

    def test_query_string_preserved(self):
        """失败标记/查询串必须随镜像保留（下载桩按子串判定失败依赖此行为）。"""
        candidates = _mirror_urls("http://i0.hdslb.com/a.jpg?broken=1")
        assert candidates[1] == "http://i2.hdslb.com/a.jpg?broken=1"
        assert all(url.endswith("?broken=1") for url in candidates)


@pytest.fixture
def download_stub(monkeypatch):
    """替换 download_stream：写假字节并返回大小。

    fail_markers：URL 包含任一标记则始终失败；fail_once_markers：只失败第一次
    （用于验证自动重试）。用"标记 + 子串"而非完整 URL 匹配，这样镜像回退
    （i0→i2→i1）的各变体都会命中同一失败条件。
    """
    state = {"calls": [], "fail_markers": set(), "fail_once_markers": set()}

    def fake_download(url, path, headers=None, **kwargs):
        state["calls"].append(url)
        if any(marker in url for marker in state["fail_markers"]):
            raise IOError("模拟下载失败")
        for marker in list(state["fail_once_markers"]):
            if marker in url:
                state["fail_once_markers"].discard(marker)
                raise IOError("模拟瞬时失败")
        data = f"data:{url}".encode()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(data)
        callback = kwargs.get("progress_cb")
        if callback is not None:
            callback(len(data), len(data))
        return len(data)

    monkeypatch.setattr("src.services.dynamic.download_stream", fake_download)
    return state


def make_service(tmp_path, item, opus_data=None, comments=None):
    session = FakeSession(item, opus_data)
    service = DynamicService(session=session, default_dir=tmp_path)
    service.reply_service = FakeReply(items=comments or [{"rpid": 1}])
    return service, session


PROGRESS_OPTIONS = dict(progress=BatchProgress(n=99, label="test", display=False))


def dynamic_dir_of(tmp_path, item):
    info = DynamicService.parse_item(item)
    date = DynamicService.dynamic_date(info)
    return tmp_path / str(info.author.mid) / date[:7] / f"{date}_1", info, date


class TestDownloadDrawLottery:
    def test_full_layout_and_links(self, tmp_path, download_stub):
        item = load_item("draw_lottery.json")
        service, session = make_service(tmp_path, item)
        result = service.download_dynamic(1250464970768908294, **PROGRESS_OPTIONS)

        assert result.cached is False
        dyn_dir, info, date = dynamic_dir_of(tmp_path, item)
        assert result.path == dyn_dir
        up_dir = tmp_path / "36081646"
        assert result.md_path == dyn_dir / "dynamic.md"

        # 动态目录内容 + 完成标记
        for name in ("dynamic.md", "dynamic.json", "raw.json", "comments.json", "dynamic_id.txt"):
            assert (dyn_dir / name).is_file(), name
        assert (dyn_dir / "dynamic_id.txt").read_text(encoding="utf-8").strip() == "1250464970768908294"

        # 图片：全目录连续编号（账本 done）
        images_dir = up_dir / "_assets" / "images"
        assert (images_dir / f"{date}_1.png").is_file()
        assert (images_dir / f"{date}_2.jpg").is_file()
        ledger = json.loads((images_dir / "index.json").read_text(encoding="utf-8"))
        assert {key: entry["status"] for key, entry in ledger["entries"].items()} == {
            "1250464970768908294/image/1": "done",
            "1250464970768908294/image/2": "done",
        }

        # 表情 / 头像 / 装扮卡 / 资料快照
        assert (up_dir / "_assets" / "emojis" / "10238" / "送花.gif").is_file()
        assert (up_dir / "_assets" / "avatar_洛天依.png").is_file()
        assert (up_dir / "_assets" / "decorate_洛天依八音奇响.png").is_file()
        assert (up_dir / "_assets" / "profile.json").is_file()
        manifest = json.loads((up_dir / "_assets" / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["emojis"]["10238/145978"]["file"] == "送花.gif"
        assert manifest["emojis"]["10238/145971"]["file"] == "魔法.gif"

        # md 相对引用与 render 内容
        md = (dyn_dir / "dynamic.md").read_text(encoding="utf-8")
        assert f"../../_assets/images/{date}_1.png" in md
        assert "../../_assets/emojis/10238/送花.gif" in md

        # dynamic.json 关键字段 + 图片 file 回填
        payload = json.loads((dyn_dir / "dynamic.json").read_text(encoding="utf-8"))
        assert payload["lottery"] == {"rid": "425833"}
        assert payload["media"]["images"][0]["file"] == f"../../_assets/images/{date}_1.png"
        assert payload["download"]["failures"] == []

        # 评论：公共入口直接使用已知 oid/type（默认 20 条热评）
        comments = json.loads((dyn_dir / "comments.json").read_text(encoding="utf-8"))
        assert comments["count"] == 1 and comments["sort"] == "hot"
        assert service.reply_service.calls == [(409870383, 11, "hot", 20)]

    def test_second_download_is_cached(self, tmp_path, download_stub):
        item = load_item("draw_lottery.json")
        service, session = make_service(tmp_path, item)
        service.download_dynamic(1250464970768908294, **PROGRESS_OPTIONS)
        download_stub["calls"].clear()

        result = service.download_dynamic(1250464970768908294, **PROGRESS_OPTIONS)

        assert result.cached is True
        assert download_stub["calls"] == []
        assert result.md_path is not None and result.md_path.is_file()

    def test_force_redownload_reuses_numbers(self, tmp_path, download_stub):
        item = load_item("draw_lottery.json")
        service, _ = make_service(tmp_path, item)
        service.download_dynamic(1250464970768908294, **PROGRESS_OPTIONS)
        dyn_dir, _, date = dynamic_dir_of(tmp_path, item)
        images_dir = tmp_path / "36081646" / "_assets" / "images"
        before = sorted(p.name for p in images_dir.iterdir() if p.suffix in {".png", ".jpg"})
        download_stub["calls"].clear()

        result = service.download_dynamic(1250464970768908294, force=True, **PROGRESS_OPTIONS)

        assert result.cached is False
        assert len(download_stub["calls"]) > 0
        after = sorted(p.name for p in images_dir.iterdir() if p.suffix in {".png", ".jpg"})
        assert before == after  # 复用账本原文件名，不产生重复文件

    def test_media_failure_leaves_failed_marker_and_retry_completes(self, tmp_path, download_stub):
        item = load_item("draw_lottery.json")
        service, _ = make_service(tmp_path, item)
        second_image_url = DynamicService.parse_item(item).images[1].url
        # 以路径片段为失败标记：镜像回退（i0→i2→i1）的变体同样命中
        download_stub["fail_markers"].add("4583444d9a3e32b995ccfafbc8b8517536081646.jpg")

        first = service.download_dynamic(1250464970768908294, **PROGRESS_OPTIONS)

        dyn_dir, _, date = dynamic_dir_of(tmp_path, item)
        assert len(first.failures) == 1
        assert not (dyn_dir / "dynamic_id.txt").exists()  # 失败 → 无成功标记
        assert (dyn_dir / "dynamic_id_failed.txt").is_file()  # 失败标记（内容为动态 ID）
        assert (dyn_dir / "dynamic_id_failed.txt").read_text(encoding="utf-8").strip() == "1250464970768908294"
        assert (dyn_dir / "dynamic.json").is_file()  # 未完成目录可被重跑识别
        # 自动重试：同一原 URL 在一次运行内被尝试两次（每次各自尝试全部镜像）
        assert download_stub["calls"].count(second_image_url) == 2
        # 镜像回退：i0 失败后还尝试了 i2 / i1
        assert any("i2.hdslb.com" in url for url in download_stub["calls"])
        assert any("i1.hdslb.com" in url for url in download_stub["calls"])
        images_dir = tmp_path / "36081646" / "_assets" / "images"
        first_names = sorted(p.name for p in images_dir.iterdir() if p.suffix in {".png", ".jpg"})

        # 重跑：通过标记找到原目录，按原编号补齐缺文件，成功标记替换失败标记
        download_stub["fail_markers"].clear()
        second = service.download_dynamic(1250464970768908294, **PROGRESS_OPTIONS)

        assert second.cached is False
        assert second.path == dyn_dir
        assert second.failures == []
        assert (dyn_dir / "dynamic_id.txt").is_file()
        assert not (dyn_dir / "dynamic_id_failed.txt").exists()
        assert sorted(p.name for p in images_dir.iterdir() if p.suffix in {".png", ".jpg"}) == first_names
        assert (images_dir / f"{date}_2.jpg").stat().st_size > 0

    def test_transient_failure_recovers_within_one_run(self, tmp_path, download_stub):
        item = load_item("draw_lottery.json")
        service, _ = make_service(tmp_path, item)
        second_image_url = DynamicService.parse_item(item).images[1].url
        download_stub["fail_once_markers"].add("4583444d9a3e32b995ccfafbc8b8517536081646.jpg")

        result = service.download_dynamic(
            1250464970768908294, with_comments=False, **PROGRESS_OPTIONS
        )

        assert result.failures == []
        assert (result.path / "dynamic_id.txt").is_file()
        assert not (result.path / "dynamic_id_failed.txt").exists()
        # i0 失败一次后由镜像 i2 顶上，无需触发整任务重试
        assert download_stub["calls"].count(second_image_url) == 1
        assert any("i2.hdslb.com" in url for url in download_stub["calls"])

    def test_without_comments(self, tmp_path, download_stub):
        item = load_item("draw_lottery.json")
        service, _ = make_service(tmp_path, item)
        result = service.download_dynamic(
            1250464970768908294, with_comments=False, **PROGRESS_OPTIONS
        )
        assert result.comments_path is None
        assert not (result.path / "comments.json").exists()

    def test_comment_failure_does_not_block(self, tmp_path, download_stub):
        item = load_item("draw_lottery.json")
        service, _ = make_service(tmp_path, item)
        service.reply_service = FakeReply(error=RuntimeError("评论接口炸了"))
        result = service.download_dynamic(1250464970768908294, **PROGRESS_OPTIONS)
        assert result.comments_path is None
        assert any("评论获取失败" in warning for warning in result.warnings)
        assert (result.path / "dynamic_id.txt").is_file()  # 评论失败不影响完成


class TestDownloadArticleFullContent:
    def test_truncated_article_fetches_full_text(self, tmp_path, download_stub):
        item = load_item("article.json")
        service, session = make_service(tmp_path, item, opus_data=load_data("opus_full_article.json"))
        result = service.download_dynamic(1234141591037280323, with_comments=False, **PROGRESS_OPTIONS)

        assert session.opus_calls == 1
        payload = json.loads((result.path / "dynamic.json").read_text(encoding="utf-8"))
        assert payload["content"]["full_text_fetched"] is True
        assert "亲爱的旅行者" in payload["content"]["text"]
        md = (result.path / "dynamic.md").read_text(encoding="utf-8")
        assert "亲爱的旅行者" in md


class TestDownloadForward:
    def test_orig_written_to_its_author_dir(self, tmp_path, download_stub):
        item = load_item("forward.json")
        item["orig"]["modules"]["module_author"]["mid"] = 12345
        item["orig"]["modules"]["module_author"]["name"] = "某UP"
        service, _ = make_service(tmp_path, item)

        result = service.download_dynamic(1251781631619891203, with_comments=False, **PROGRESS_OPTIONS)

        assert len(result.forwarded) == 1
        orig_result = result.forwarded[0]
        orig_info = DynamicService.parse_item(item["orig"])
        orig_date = DynamicService.dynamic_date(orig_info)
        expected_orig_dir = tmp_path / "12345" / orig_date[:7] / f"{orig_date}_1"
        assert orig_result.path == expected_orig_dir
        assert (expected_orig_dir / "dynamic_id.txt").is_file()

        md = (result.path / "dynamic.md").read_text(encoding="utf-8")
        assert "## 转发自 某UP (12345)" in md
        assert "> 本地存档：" in md
        assert "原动态图片" in md
        # 原动态图片引用：从主动态目录指向原作者的 _assets
        assert "12345/_assets/images/" in md

    def test_deleted_orig_placeholder(self, tmp_path, download_stub):
        item = load_item("forward.json")
        item["orig"] = {"id_str": "1245270529937506306", "type": "DYNAMIC_TYPE_DELETED", "modules": None}
        service, _ = make_service(tmp_path, item)

        result = service.download_dynamic(1251781631619891203, with_comments=False, **PROGRESS_OPTIONS)

        assert result.forwarded == []
        md = (result.path / "dynamic.md").read_text(encoding="utf-8")
        assert "> 原动态已删除" in md

    def test_forward_depth_limit(self, tmp_path, download_stub):
        item = load_item("forward.json")
        service, _ = make_service(tmp_path, item)

        result = service.download_dynamic(
            1251781631619891203, with_comments=False, max_forward_depth=0, **PROGRESS_OPTIONS
        )

        assert result.forwarded == []
        assert any("超过转发递归深度" in warning for warning in result.warnings)


class TestLivePhoto:
    def test_live_url_creates_video_file(self, tmp_path, download_stub):
        item = load_item("draw_lottery.json")
        pics = item["modules"]["module_dynamic"]["major"]["opus"]["pics"]
        pics[0]["live_url"] = "https://example.com/live.m4s"
        service, _ = make_service(tmp_path, item)

        result = service.download_dynamic(1250464970768908294, with_comments=False, **PROGRESS_OPTIONS)

        _, _, date = dynamic_dir_of(tmp_path, item)
        images_dir = tmp_path / "36081646" / "_assets" / "images"
        assert (images_dir / f"{date}_1.png").is_file()  # 静帧
        assert (images_dir / f"{date}_2.m4s").is_file()  # 动态图视频（编号顺延）
        assert (images_dir / f"{date}_3.jpg").is_file()  # 第二张图顺延
        payload = json.loads((result.path / "dynamic.json").read_text(encoding="utf-8"))
        assert payload["media"]["images"][0]["live_file"].endswith(f"{date}_2.m4s")
        md = (result.path / "dynamic.md").read_text(encoding="utf-8")
        # 静帧图片 + <video> 标签（支持 HTML 的渲染器播放，否则显示图片）
        assert f"![01](../../_assets/images/{date}_1.png)" in md
        assert f'<video src="../../_assets/images/{date}_2.m4s" poster="../../_assets/images/{date}_1.png" controls></video>' in md


@pytest.mark.network
class TestNetworkDownload:
    """真实网络用例（默认跳过，--network 启用）：完整下载示例动态。"""

    def test_download_real_dynamic(self, tmp_path):
        service = DynamicService(default_dir=tmp_path)
        result = service.download_dynamic(
            "https://www.bilibili.com/opus/1250464970768908294",
            comment_max_count=5,
        )

        assert result.cached is False
        dyn_dir = result.path
        assert (dyn_dir / "dynamic.md").is_file()
        assert (dyn_dir / "dynamic.json").is_file()
        assert (dyn_dir / "comments.json").is_file()
        assert (dyn_dir / "dynamic_id.txt").read_text(encoding="utf-8").strip() == "1250464970768908294"

        images_dir = tmp_path / "36081646" / "_assets" / "images"
        image_files = [p for p in images_dir.iterdir() if p.suffix in {".png", ".jpg"}]
        assert len(image_files) >= 2
        ledger = json.loads((images_dir / "index.json").read_text(encoding="utf-8"))
        assert ledger["entries"]["1250464970768908294/image/1"]["status"] == "done"

        # 二次下载走缓存
        again = service.download_dynamic(
            "https://www.bilibili.com/opus/1250464970768908294",
            comment_max_count=5,
        )
        assert again.cached is True
