"""RiskGate 风控协调器的单元测试。

核心约定：任一线程触发风控后，所有线程在下一次获取信息前各自随机暂停（每个线程
暂停一次、时长单独计算）；无风控事件时不产生任何暂停。
"""

import threading

import pytest

from src.util.risk_gate import RiskGate


def _patch_sleep(monkeypatch):
    """替换 risk_gate 模块里的 time.sleep，记录暂停时长。"""
    sleeps = []

    def _record(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("src.util.risk_gate.time.sleep", _record)
    return sleeps


def test_no_risk_no_pause(monkeypatch):
    gate = RiskGate()
    sleeps = _patch_sleep(monkeypatch)
    gate.pause_before_fetch()
    gate.pause_before_fetch()
    assert sleeps == []  # 没有风控事件，从不暂停


def test_pause_once_per_risk_event(monkeypatch):
    gate = RiskGate()
    sleeps = _patch_sleep(monkeypatch)
    gate.mark_risk()
    gate.pause_before_fetch()
    gate.pause_before_fetch()  # 已消费，不再暂停
    assert len(sleeps) == 1


def test_pause_duration_in_range(monkeypatch):
    gate = RiskGate()
    sleeps = _patch_sleep(monkeypatch)
    gate.mark_risk()
    gate.pause_before_fetch()
    assert 3.0 <= sleeps[0] <= 8.0


def test_multiple_risk_events_pause_each(monkeypatch):
    gate = RiskGate()
    sleeps = _patch_sleep(monkeypatch)
    gate.mark_risk()
    gate.pause_before_fetch()
    gate.mark_risk()  # 又一轮风控
    gate.pause_before_fetch()
    assert len(sleeps) == 2  # 每轮风控各暂停一次


def test_each_thread_pauses_independently(monkeypatch):
    """3 个线程并发调用：每个线程恰好暂停一次（互不影响）。"""
    gate = RiskGate()
    sleeps = _patch_sleep(monkeypatch)
    gate.mark_risk()

    n = 3
    barrier = threading.Barrier(n)  # 所有线程等同一个 barrier，尽量同时开始

    def worker(_i):
        barrier.wait()
        gate.pause_before_fetch()
        gate.pause_before_fetch()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(sleeps) == n  # 每个线程独立暂停一次
