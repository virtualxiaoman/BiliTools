"""批量下载进度显示（BatchProgress）的单元测试。"""

from src.models import VideoQuality
from src.util.progress import BatchProgress


class TestBatchProgress:
    def test_single_stream_update(self, capsys):
        p = BatchProgress(n=1, display=True)
        p.start(1, "a.mp4")
        p.update(5242880, 10485760)  # 5/10MB
        p.update(10485760, 10485760)
        p.finish()
        out = capsys.readouterr().out
        assert "[1/1]" in out
        assert "a.mp4" in out
        assert "5.0/10.0MB (50.0%)" in out
        assert "100.0%" in out

    def test_quality_tag_between_name_and_mb(self, capsys):
        """清晰度标签应出现在名称和 MB 进度之间。"""
        p = BatchProgress(n=1, display=True)
        p.start(1, "测试.mp4")
        p.set_quality(VideoQuality.HD4K)
        p.update(5242880, 10485760)
        p.finish()
        out = capsys.readouterr().out
        assert "[测试.mp4] [4K]: 5.0/10.0MB" in out  # 名称 → [4K] → 进度

    def test_set_quality_before_any_bytes_no_spurious_line(self, capsys):
        """set_quality 在无进度时不应输出一行空进度。"""
        p = BatchProgress(n=1, display=True)
        p.start(1, "v.mp4")
        p.set_quality(VideoQuality.P1080)
        out = capsys.readouterr().out
        assert "0.0" not in out  # 没有渲染空进度行

    def test_no_quality_tag_when_unset(self, capsys):
        p = BatchProgress(n=1, display=True)
        p.start(1, "x.bin")
        p.update(10, 100)
        p.finish()
        out = capsys.readouterr().out
        assert "[x.bin]: 0.0" in out  # 无 [清晰度] 段

    def test_multi_stream_incremental(self, capsys):
        """视频流+音频流：字节跨流累计，总大小为两流之和。"""
        p = BatchProgress(n=1, display=True)
        p.start(1, "v.mp4")
        # 视频流 100MB
        p.add(30_000_000, 100_000_000, stream_id=0)
        p.add(70_000_000, 100_000_000, stream_id=0)
        # 音频流 8MB（第一阶段 5MB → 累计 105/108MB = 97.2%）
        p.add(5_000_000, 8_000_000, stream_id=1)
        p.add(3_000_000, 8_000_000, stream_id=1)
        p.finish()
        out = capsys.readouterr().out
        assert p.current_done == 108_000_000
        assert p._grand_total() == 108_000_000
        # 音频流中间态：累计 105/108MB → 97.2%
        assert "97.2%" in out
        # 视频流阶段显示的是当前流总大小
        assert "95.4MB" in out

    def test_no_total_shows_dash(self, capsys):
        p = BatchProgress(n=1, display=True)
        p.start(1, "x.bin")
        p.update(12345678, None)  # 无 Content-Length
        p.finish()
        out = capsys.readouterr().out
        assert "--%" in out

    def test_status_message(self, capsys):
        p = BatchProgress(n=1, display=True)
        p.start(1, "v.mp4")
        p.status("正在合成...")
        out = capsys.readouterr().out
        assert "正在合成" in out

    def test_silent_when_display_false(self, capsys):
        p = BatchProgress(n=1, display=False)
        p.start(1, "v.mp4")
        p.update(10, 100)
        p.status("x")
        p.finish()
        assert capsys.readouterr().out == ""

    def test_iter_count(self):
        p = BatchProgress(n=3)
        assert list(p.iter_count()) == [1, 2, 3]

    def test_stream_totals_dedupe_by_stream_id(self):
        """同一流多次回调只记一次总大小。"""
        p = BatchProgress(n=1, display=False)
        p.start(1, "v.mp4")
        p.add(1, 100, stream_id=0)
        p.add(2, 100, stream_id=0)  # 同流，total 相同
        assert p._grand_total() == 100  # 不是 200
