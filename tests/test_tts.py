"""TtsService 单元测试（不联网、不真正拉起服务）：假 HTTP/假进程驱动接口行为。"""

import pathlib
import sys
import time
from urllib.parse import quote

import pytest
import requests

from src.services.tts import (
    TtsService,
    _resolve_python,
    _resolve_server_script,
    _server_script_candidates,
)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, content=b"", headers=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.content = content
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("no json body")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeHttp:
    """假 requests.Session：按 (method, url) 返回预置响应。"""

    def __init__(self, get_responses=None, post_response=None):
        self.get_responses = get_responses or {}
        self.post_response = post_response
        self.posts = []

    def get(self, url, timeout=None):
        resp = self.get_responses.get(url)
        if resp is None:
            raise requests.ConnectionError("connection refused")
        return resp

    def post(self, url, json=None, timeout=None):
        self.posts.append((url, json, timeout))
        return self.post_response

    def close(self):
        pass


def _service(http, **kwargs):
    return TtsService(session=http, **kwargs)


def test_health_ok_and_down(monkeypatch):
    monkeypatch.delenv("TTS_SERVER_URL", raising=False)
    http = FakeHttp({"http://t/health": FakeResponse(json_data={"status": "ok", "model_loaded": True})})
    assert _service(http, base_url="http://t").health() == {"status": "ok", "model_loaded": True}

    down = _service(FakeHttp(), base_url="http://t")
    assert down.health() is None  # 连接被拒 → None 而不是抛异常
    assert down.base_url == "http://t"
    assert TtsService(session=FakeHttp()).base_url == "http://127.0.0.1:9881"  # 默认地址


def test_list_roles():
    http = FakeHttp({"http://t/roles": FakeResponse(json_data=[{"name": "阿罗娜（中配）", "note": ""}])})
    roles = _service(http, base_url="http://t").list_roles()
    assert roles == [{"name": "阿罗娜（中配）", "note": ""}]

    with pytest.raises(RuntimeError, match="角色列表"):
        _service(FakeHttp(), base_url="http://t").list_roles()


def test_synthesize_posts_payload_and_returns_server_path():
    wav_path = r"G:\GPT-SoVITS\outputs\阿罗娜（中配）_1.wav"
    http = FakeHttp(
        {"http://t/health": FakeResponse(json_data={"status": "ok"})},
        FakeResponse(content=b"RIFF...", headers={"X-Wav-Path": quote(wav_path)}),
    )
    result = _service(http, base_url="http://t").synthesize("阿罗娜（中配）", "你好", lang="zh", speed=1.1)
    assert str(result) == wav_path  # X-Wav-Path 的 URL 编码已还原
    url, payload, timeout = http.posts[0]
    assert url == "http://t/tts"
    assert payload == {"role": "阿罗娜（中配）", "text": "你好", "lang": "zh", "speed": 1.1, "seed": -1}
    assert timeout == (5, 300.0)


def test_synthesize_save_to_writes_bytes(tmp_path):
    http = FakeHttp(
        {"http://t/health": FakeResponse(json_data={"status": "ok"})},
        FakeResponse(content=b"RIFF-data", headers={"X-Wav-Path": "ignored.wav"}),
    )
    target = tmp_path / "voice" / "a.wav"
    result = _service(http, base_url="http://t").synthesize("r", "hi", save_to=target)
    assert result == target and target.read_bytes() == b"RIFF-data"


def test_synthesize_raises_when_service_down_without_autostart(monkeypatch):
    monkeypatch.setattr("src.services.tts._server_script_candidates", lambda: [])  # 确保不碰真实仓库
    service = _service(FakeHttp(), base_url="http://t", autostart=False)
    with pytest.raises(RuntimeError, match="TTS 服务未启动"):
        service.synthesize("r", "hi")


def test_synthesize_validates_input():
    service = _service(FakeHttp(), base_url="http://t")
    with pytest.raises(ValueError, match="不能为空"):
        service.synthesize("r", "   ")
    with pytest.raises(ValueError, match="不支持的语言"):
        service.synthesize("r", "hi", lang="fr")


def test_synthesize_http_error_carries_detail():
    http = FakeHttp(
        {"http://t/health": FakeResponse(json_data={"status": "ok"})},
        FakeResponse(status_code=404, json_data={"detail": "未注册的角色: x"}),
    )
    with pytest.raises(RuntimeError, match="未注册的角色"):
        _service(http, base_url="http://t").synthesize("x", "hi")


# ---- autostart 默认与脚本/解释器解析 ----

def test_autostart_defaults_to_true(monkeypatch):
    monkeypatch.delenv("TTS_SERVER_URL", raising=False)
    assert TtsService(session=FakeHttp()).autostart is True
    assert TtsService(session=FakeHttp(), autostart=False).autostart is False


def test_server_script_candidates_env_first(monkeypatch, tmp_path):
    fake = tmp_path / "tts_server.py"
    monkeypatch.setenv("TTS_SERVER_SCRIPT", str(fake))
    candidates = _server_script_candidates()
    assert candidates[0] == fake
    assert all(str(candidate).endswith("tts_server.py") for candidate in candidates)


def test_resolve_server_script_prefers_existing(monkeypatch, tmp_path):
    missing, existing = tmp_path / "missing.py", tmp_path / "tts_server.py"
    existing.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr("src.services.tts._server_script_candidates", lambda: [missing, existing])
    assert _resolve_server_script() == existing

    monkeypatch.setattr("src.services.tts._server_script_candidates", lambda: [missing])
    assert _resolve_server_script() is None


def test_resolve_python_env_then_conda_then_fallback(monkeypatch, tmp_path):
    script = tmp_path / "tts_server.py"
    fake_python = tmp_path / "python.exe"
    fake_python.write_text("", encoding="utf-8")

    monkeypatch.setenv("TTS_PYTHON", str(fake_python))
    assert _resolve_python(script) == str(fake_python)  # 环境变量优先

    monkeypatch.delenv("TTS_PYTHON", raising=False)
    home = tmp_path / "home"
    conda_python = home / ".conda" / "envs" / "GPTSoVits" / "python.exe"
    conda_python.parent.mkdir(parents=True)
    conda_python.write_text("", encoding="utf-8")
    monkeypatch.setattr(pathlib.Path, "home", staticmethod(lambda: home))
    assert _resolve_python(script) == str(conda_python)  # 常见 conda 环境

    conda_python.unlink()
    assert _resolve_python(script) == sys.executable  # 最后回退当前解释器


def test_ensure_server_reports_searched_paths_when_script_missing(monkeypatch):
    monkeypatch.setattr("src.services.tts._server_script_candidates",
                        lambda: [pathlib.Path("Z:/nope/tts_server.py")])
    with pytest.raises(RuntimeError) as excinfo:
        _service(FakeHttp(), base_url="http://t").ensure_server()
    message = str(excinfo.value)
    assert "未找到 tts_server.py" in message and "TTS_SERVER_SCRIPT" in message
    assert "Z:/nope/tts_server.py" in message.replace("\\", "/")  # 报错里列出已查找的候选


def test_synthesize_autostart_without_script_gives_hint(monkeypatch):
    monkeypatch.setattr("src.services.tts._server_script_candidates", lambda: [])
    service = _service(FakeHttp(), base_url="http://t")  # autostart 默认 True
    with pytest.raises(RuntimeError, match="TTS_SERVER_SCRIPT"):
        service.synthesize("r", "hi")


def test_ensure_server_spawns_and_waits(monkeypatch, tmp_path):
    script = tmp_path / "tts_server.py"
    script.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr("src.services.tts._server_script_candidates", lambda: [script])
    spawned = {}

    class RunningProc:
        def poll(self):
            return None

    def fake_popen(argv, **kwargs):
        spawned["argv"], spawned["kwargs"] = argv, kwargs
        return RunningProc()

    monkeypatch.setattr("src.services.tts.subprocess.Popen", fake_popen)
    service = _service(FakeHttp(), base_url="http://127.0.0.1:9881")
    monkeypatch.setattr(service, "health", lambda: {"status": "ok"})  # 拉起后立即可用

    service.ensure_server(wait_s=5)

    assert spawned["argv"][1] == str(script)
    assert spawned["argv"][2:] == ["-a", "127.0.0.1", "-p", "9881"]
    assert spawned["kwargs"]["cwd"] == str(tmp_path)


def test_ensure_server_tolerates_exited_process_when_port_answers(monkeypatch, tmp_path):
    """并发拉起：新进程退出但端口已有服务（另一个实例）→ 视为就绪。"""
    script = tmp_path / "tts_server.py"
    script.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr("src.services.tts._server_script_candidates", lambda: [script])

    class DeadProc:
        def poll(self):
            return 0  # 立即退出（端口被另一个实例占用）

    monkeypatch.setattr("src.services.tts.subprocess.Popen", lambda *a, **k: DeadProc())

    class FakeTime:
        def __init__(self):
            self.slept = 0.0

        def sleep(self, seconds):
            self.slept += seconds

        def time(self):
            return time.time()

        def strftime(self, fmt):
            return time.strftime(fmt)

    fake_time = FakeTime()
    monkeypatch.setattr("src.services.tts.time", fake_time)

    service = _service(FakeHttp(), base_url="http://127.0.0.1:9881")
    calls = {"n": 0}

    def fake_health():
        calls["n"] += 1
        return None if calls["n"] == 1 else {"status": "ok"}

    monkeypatch.setattr(service, "health", fake_health)
    service.ensure_server(wait_s=5)

    assert calls["n"] == 2 and fake_time.slept >= 1.0
