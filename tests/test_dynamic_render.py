"""动态渲染测试（离线）：Markdown 黄金文件 + JSON 结构。"""

import json
import posixpath
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.services.dynamic import DynamicService
from src.services.dynamic_render import info_to_dict, render_markdown

FIXTURES = Path(__file__).parent / "fixtures" / "dynamic"

# 固定"数据统计"时间，保证黄金文件可复现
FETCHED_AT = datetime(2026, 10, 2, 13, 10, tzinfo=timezone(timedelta(hours=8)))


def load_item(name: str) -> dict:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "item" in data:
        data = data["item"]
    return data


def parse(name: str):
    return DynamicService.parse_item(load_item(name))


def prepared_draw_lottery():
    """模拟下载完成后的落盘回填（编号示例：全目录连续口径）。"""
    info = parse("draw_lottery.json")
    info.images[0].file = "../../_assets/images/2026-09-21_253.png"
    info.images[1].file = "../../_assets/images/2026-09-21_254.jpg"
    info.emojis[0].file = "../../_assets/emojis/10238/送花.gif"
    info.emojis[1].file = "../../_assets/emojis/10238/魔法.gif"
    return info


class TestMarkdownGolden:
    def test_draw_lottery_matches_golden(self):
        expected = (FIXTURES / "golden_draw_lottery.md").read_text(encoding="utf-8")
        assert render_markdown(prepared_draw_lottery(), fetched_at=FETCHED_AT) == expected

    def test_emoji_falls_back_to_remote_url(self):
        info = parse("draw_lottery.json")
        md = render_markdown(info, fetched_at=FETCHED_AT)
        assert "![送花](https://i0.hdslb.com/" in md

    def test_pub_time_and_stats_timestamp(self):
        """发布时间用 pub_ts 渲染完整日期时间；数据行后附统计时间戳。"""
        info = parse("draw_lottery.json")
        md = render_markdown(info, fetched_at=FETCHED_AT)
        assert "> 作者：洛天依 (36081646) ｜ 2026-09-21 18:02 ｜ 图文动态（含互动抽奖）" in md
        assert "> 数据统计日期是26.10.02 13:10" in md

    def test_short_pub_time_expanded(self):
        """接口只给"9月1日"短格式时，仍按 pub_ts 输出完整时间。"""
        info = parse("forward.json")
        info.author.pub_time = "9月25日"
        md = render_markdown(info, fetched_at=FETCHED_AT)
        assert "9月25日" not in md
        assert "2026-09-25" in md


class TestMarkdownSections:
    def test_truncated_note(self):
        info = parse("article.json")
        md = render_markdown(info)
        assert "> 注：正文为摘要，全文见原文链接" in md

    def test_forward_quote_with_relative_refs(self):
        info = parse("forward.json")
        info.forward.archive_dir = "../2026-09-18_1"
        image = info.forward.orig.images[0]
        image.file = "../../_assets/images/2026-09-18_87.png"
        md = render_markdown(info)
        assert "## 转发自 洛天依 (36081646)" in md
        assert "> 本地存档：../2026-09-18_1" in md
        expected_ref = posixpath.normpath(
            posixpath.join("../2026-09-18_1", "../../_assets/images/2026-09-18_87.png")
        )
        assert f"![原01]({expected_ref})" in md

    def test_deleted_forward_placeholder(self):
        info = parse("forward.json")
        info.forward.deleted = True
        info.forward.orig = None
        md = render_markdown(info)
        assert "> 原动态已删除" in md

    def test_word_dynamic(self):
        info = parse("word.json")
        md = render_markdown(info)
        assert md.startswith("# 本号主要用于测试")
        assert "纯文字动态" in md

    def test_archive_card_url_normalized(self):
        info = parse("archive.json")
        card = info.cards[0]
        assert card.jump_url.startswith("https://")
        md = render_markdown(info, fetched_at=FETCHED_AT)
        assert "- 链接：https://www.bilibili.com/video/BV1khaA6hECW" in md
        # 封面以图片内联展示，而不是标题/路径文本
        assert "![封面](http" in md
        assert "封面：" not in md
        # archive 卡片不再重复渲染视频简介
        assert "- 说明：" not in md

    def test_goods_card_embeds_cover_images(self):
        info = parse("goods.json")
        md = render_markdown(info, fetched_at=FETCHED_AT)
        assert "## 卡片：商品" in md
        assert "  - ![封面](https://i1.hdslb.com/" in md
        assert "封面：" not in md


class TestInfoToDict:
    def test_draw_lottery_schema(self):
        info = prepared_draw_lottery()
        payload = info_to_dict(info)
        assert payload["schema_version"] == 1
        assert payload["id"] == "1250464970768908294"
        assert payload["kind"] == "draw"
        assert payload["author"]["mid"] == 36081646
        assert payload["lottery"] == {"rid": "425833"}
        assert payload["vote"] is None
        assert payload["forward"] is None
        assert payload["stats"] == {"like": 6387, "comment": 555, "forward": 7387}
        image = payload["media"]["images"][0]
        assert image["file"] == "../../_assets/images/2026-09-21_253.png"
        assert image["width"] == 3400
        assert payload["media"]["emojis"][0]["package_id"] == "10238"
        assert payload["content"]["truncated"] is False

    def test_forward_schema(self):
        info = parse("forward.json")
        payload = info_to_dict(info)
        assert payload["forward"]["orig_id"] == 1245270529937506306
        assert payload["forward"]["deleted"] is False

    def test_json_serializable(self):
        info = prepared_draw_lottery()
        text = json.dumps(info_to_dict(info), ensure_ascii=False)
        assert '"schema_version": 1' in text
