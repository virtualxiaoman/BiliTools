"""动态解析测试（离线，基于真实 API 响应 fixtures）。"""

import json
from pathlib import Path

import pytest

from src.services.dynamic import DynamicService

FIXTURES = Path(__file__).parent / "fixtures" / "dynamic"


def load_item(name: str) -> dict:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "item" in data:
        data = data["item"]
    return data


def parse(name: str):
    return DynamicService.parse_item(load_item(name))


class TestResolveDynamicId:
    @pytest.mark.parametrize("value,expected", [
        ("1250464970768908294", 1250464970768908294),
        (1250464970768908294, 1250464970768908294),
        ("https://www.bilibili.com/opus/1250464970768908294", 1250464970768908294),
        ("https://www.bilibili.com/opus/1250464970768908294?spm_id_from=333.999", 1250464970768908294),
        ("https://m.bilibili.com/opus/1250464970768908294/", 1250464970768908294),
        ("https://t.bilibili.com/943536810962714642", 943536810962714642),
    ])
    def test_accepts_id_and_links(self, value, expected):
        assert DynamicService.resolve_dynamic_id(value) == expected

    @pytest.mark.parametrize("bad", [
        "", "   ", "abc", 0, -1,
        "https://www.bilibili.com/video/BV1ov42117yC",
        "https://b23.tv/abcdef",
    ])
    def test_rejects_invalid(self, bad):
        with pytest.raises(ValueError):
            DynamicService.resolve_dynamic_id(bad)


class TestDrawLottery:
    """示例动态：图文 + 互动抽奖 + 内联表情 + 网页链接。"""

    def test_basic_fields(self):
        info = parse("draw_lottery.json")
        assert info.kind == "draw"
        assert info.id == 1250464970768908294
        assert info.url == "https://www.bilibili.com/opus/1250464970768908294"
        assert info.author.mid == 36081646
        assert info.author.name == "洛天依"
        assert info.comment_oid == 409870383
        assert info.comment_type == 11

    def test_stats_and_topic(self):
        info = parse("draw_lottery.json")
        assert (info.stats.like, info.stats.comment, info.stats.forward) == (6387, 555, 7387)
        assert info.topic is not None
        assert info.topic.name == "洛天依2026巡演"

    def test_images(self):
        info = parse("draw_lottery.json")
        assert len(info.images) == 2
        first, second = info.images
        assert (first.index, first.width, first.height) == (1, 3400, 1988)
        assert (second.width, second.height) == (1250, 12400)
        assert first.url.startswith("https://") or first.url.startswith("http://")
        assert first.live_url == ""

    def test_rich_blocks(self):
        info = parse("draw_lottery.json")
        types = [block["type"] for block in info.content.blocks]
        assert types[0] == "lottery"
        assert "emoji" in types and "link" in types
        lottery = info.content.blocks[0]
        assert lottery["rid"] == "425833"
        assert info.lottery_rid == "425833"
        link = next(b for b in info.content.blocks if b["type"] == "link")
        assert "show.bilibili.com" in link["url"]

    def test_inline_emojis(self):
        info = parse("draw_lottery.json")
        assert len(info.emojis) == 2
        flower = info.emojis[0]
        assert flower.short_name == "送花"
        assert flower.package_id == "10238"
        assert flower.url.endswith(".gif")
        assert info.content.text.startswith("互动抽奖")
        assert info.content.truncated is False


class TestLegacyDraw:
    """旧式表示（major.draw、无 summary）：正文缺失但图片仍可解析。"""

    def test_fallback_representation(self):
        info = parse("legacy_draw.json")
        assert info.kind == "draw"
        assert len(info.images) == 2
        assert info.content.text == ""
        assert info.content.blocks == []


class TestWord:
    def test_text_only_with_emoji(self):
        info = parse("word.json")
        assert info.kind == "word"
        assert "本号主要用于测试" in info.content.text
        assert [b["type"] for b in info.content.blocks] == ["text", "emoji"]
        assert info.emojis[0].short_name == "doge"


class TestForward:
    def test_forward_and_orig(self):
        info = parse("forward.json")
        assert info.kind == "forward"
        assert info.forward is not None
        assert info.forward.deleted is False
        assert info.forward.orig_id == 1245270529937506306
        assert info.forward.orig is not None
        assert info.forward.orig.kind == "draw"
        assert len(info.forward.orig.images) == 2

    def test_mention_block(self):
        info = parse("forward.json")
        mention = next(b for b in info.content.blocks if b["type"] == "mention")
        assert mention["text"].startswith("@")
        assert mention["mid"] > 0


class TestArchive:
    def test_archive_card(self):
        info = parse("archive.json")
        assert info.kind == "archive"
        assert info.cards and info.cards[0].kind == "archive"
        card = info.cards[0]
        assert card.bvid == "BV1khaA6hECW"
        assert card.title
        assert card.cover_url.startswith("http")
        assert info.images == []


class TestArticle:
    def test_truncated_flag(self):
        info = parse("article.json")
        assert info.kind == "article"
        assert info.content.truncated is True
        assert "Transformer" in info.content.title


class TestCommonSquare:
    def test_dressup_card(self):
        info = parse("common_square.json")
        assert info.kind == "common"
        card = info.cards[0]
        assert card.kind == "common"
        assert "洛天依14周年勋章" in card.title
        assert card.cover_url.startswith("http")


class TestAdditionalCards:
    def test_game_card_with_archive(self):
        info = parse("common_game.json")
        kinds = [(c.kind, c.bvid) for c in info.cards]
        assert ("archive", "BV14Baa6JENd") in kinds
        common = next(c for c in info.cards if c.kind == "common")
        assert common.extra.get("sub_type") == "game"

    def test_reserve_card(self):
        info = parse("reserve.json")
        card = next(c for c in info.cards if c.kind == "reserve")
        assert "直播预约" in card.title
        assert "lottery" in card.extra.get("desc3", {}).get("jump_url", "")

    def test_goods_items(self):
        info = parse("goods.json")
        card = next(c for c in info.cards if c.kind == "goods")
        items = card.extra.get("items") or []
        assert items and items[0]["cover"].startswith("http")
        assert items[0]["price"]


class TestOpusFullParagraphs:
    def test_parse_full_article(self):
        data = json.loads((FIXTURES / "opus_full_article.json").read_text(encoding="utf-8"))
        modules = data["item"]["modules"]
        paras = next(
            m["module_content"]["paragraphs"]
            for m in modules
            if m.get("module_type") == "MODULE_TYPE_CONTENT"
        )
        blocks, text, emojis = DynamicService.parse_paragraphs(paras)
        assert len(paras) == 333
        assert text.startswith("亲爱的旅行者：")
        assert len(text) > 5000
        assert emojis == []
        assert {b["type"] for b in blocks} <= {"text", "heading", "list", "code", "quote", "line", "image"}


class TestEmojiShortName:
    @pytest.mark.parametrize("raw,expected", [
        ("[洛天依14周年·纯蓝幻乐 动态表情包_送花]", "送花"),
        ("[doge]", "doge"),
        ("[崩坏3_琪亚娜]", "琪亚娜"),
        ("[无下划线]", "无下划线"),
        ("", "emoji"),
    ])
    def test_short_name(self, raw, expected):
        assert DynamicService.emoji_short_name(raw) == expected
