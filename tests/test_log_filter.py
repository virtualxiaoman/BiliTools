"""GUI 日志管线：原始字节进度行不进入界面，日志分类供界面过滤。"""

from frontend.pyside6.logs import (
    DEFAULT_HIDDEN_KINDS,
    LogKind,
    StdoutRedirect,
    classify_kind,
)
from frontend.pyside6.signals import LogCategory


class _FakeSignal:
    def __init__(self):
        self.messages = []

    def emit(self, category, text):
        self.messages.append(text)


class _FakeSignals:
    def __init__(self):
        self.log_message = _FakeSignal()


def test_raw_progress_render_lines_are_dropped():
    signals = _FakeSignals()
    redirect = StdoutRedirect(signals)

    redirect.write("\r[1/1] [标题(BV1xx).mp4] [1080P]: 12.3/100.0MB (12.3%)")
    redirect.write("\n[1/1] [标题(BV1xx).mp4]: 准备下载")
    redirect.write("\r[1/1] [标题(BV1xx).mp4]: 正在用 ffmpeg 合成音视频...")

    assert signals.log_message.messages == []


def test_normal_stdout_is_still_forwarded():
    signals = _FakeSignals()
    redirect = StdoutRedirect(signals)

    redirect.write("视频 BV1xx：下载 2 个文件\n")

    assert signals.log_message.messages == ["视频 BV1xx：下载 2 个文件"]


def test_bracket_progress_text_mid_line_is_kept():
    """只有以 [i/n] 开头的 SDK 直出行才过滤，正文里出现的不受影响。"""
    signals = _FakeSignals()
    redirect = StdoutRedirect(signals)

    redirect.write("合集「测试」已下载 [1/2] 个视频\n")

    assert signals.log_message.messages == ["合集「测试」已下载 [1/2] 个视频"]


def test_download_start_and_cached_lines_classified():
    assert classify_kind("正在下载 [1080P] 标题(BV1xx).mp4") == LogKind.DOWNLOAD_START
    assert classify_kind("已存在，跳过：标题(BV1xx).mp4") == LogKind.CACHED_SKIP
    assert classify_kind("已存在，跳过下载：D:\\out\\标题(BV1xx).mp4") == LogKind.CACHED_SKIP


def test_up_space_other_submission_details_classified():
    assert classify_kind("  他人稿件：BV1LKaZ6TEC9（UP主：忘川风华录）") == LogKind.UP_OTHERS
    assert classify_kind("UP主 406948651 空间共 72 条视频，其中 32 条为他人稿件。") == LogKind.TASK


def test_other_log_kinds():
    assert classify_kind("下载完成 [1080P] 标题(BV1xx).mp4") == LogKind.COMPLETED
    assert classify_kind("BV1xx：下载 2 个文件") == LogKind.TASK
    assert classify_kind("已下载 3/24 个视频") == LogKind.TASK
    assert classify_kind("视频 X 当前账号无播放权限，改用账号「B」。") == LogKind.ACCOUNT
    assert classify_kind("随便一条信息") == LogKind.OTHER
    assert classify_kind("出错了", LogCategory.ERROR) == LogKind.ERROR
    assert classify_kind("注意", LogCategory.WARN) == LogKind.WARN


def test_default_hidden_kinds():
    """默认隐藏逐文件开始、缓存跳过、联合投稿明细；其他类别默认显示。"""
    assert set(DEFAULT_HIDDEN_KINDS) == {
        LogKind.DOWNLOAD_START, LogKind.CACHED_SKIP, LogKind.UP_OTHERS,
    }
