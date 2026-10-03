"""GPT-SoVITS 语音合成服务客户端（本机 HTTP）。

[为什么是薄客户端] GPT-SoVITS 仓库的 ``tts_server.py`` 提供 /health /roles /tts 三个接口；
BiliTools 只依赖 HTTP 协议（不 import 对方项目、不引入 torch/transformers），
打包成 EXE 后依然可用。

[autostart 默认开启（2026-10-03）] 服务未启动时自动拉起 tts_server.py；
脚本与解释器按以下优先级解析（环境变量与对方的 tts_client 保持一致）：
    1) 环境变量：TTS_SERVER_SCRIPT（tts_server.py 路径）、TTS_PYTHON（解释器）
    2) 常见位置探测：GPT_SOVITS_HOME、项目上级目录（含 github/ 子目录）、用户目录下的
       GPT-SoVITS / Projects/github/GPT-SoVITS 等（见 _server_script_candidates）
    3) 解释器回退：~/.conda/envs/GPTSoVits/python.exe → 仓库内 venv → 当前解释器
    服务地址：环境变量 TTS_SERVER_URL，默认 http://127.0.0.1:9881。
    脚本找不到时不会静默失败，而是给出"设置 TTS_SERVER_SCRIPT"的明确报错。

[服务端行为（实测 2026-10-03）]
- GPU 推理全局串行；**换角色会重载权重要数秒**，一场直播应固定同一角色；
- /tts 成功返回 audio/wav 字节流，响应头 X-Wav-Path 为服务端本地 wav 路径
  （同机可直接读取/播放），中文路径做了 URL 编码；
- 服务端 outputs/ 自动清理超过 7 天的 wav。
"""

import logging
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import requests

from src.config.path import PROJECT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:9881"
DEFAULT_CONDA_ENV = "GPTSoVits"  # 对方的 conda 环境名（与 tts_client 的 DEFAULT_PYTHON 一致）
_AUTOSTART_LOG = Path(tempfile.gettempdir()) / "bilitools_tts_autostart.log"
_ALLOWED_LANGS = ("zh", "ja", "en", "ko", "yue", "auto")


def _server_script_candidates() -> list:
    """tts_server.py 的候选路径（按优先级）：环境变量 → 常见仓库位置。

    常见位置覆盖：BiliTools 项目的相邻布局（如 G:/Projects/py/BiliTools 与
    G:/Projects/github/GPT-SoVITS 平级）以及用户目录下的常见克隆位置。
    """
    candidates = []
    configured = os.environ.get("TTS_SERVER_SCRIPT")
    if configured:
        candidates.append(Path(configured))

    roots = [
        os.environ.get("GPT_SOVITS_HOME"),
        PROJECT_ROOT.parent / "GPT-SoVITS",
        PROJECT_ROOT.parent / "github" / "GPT-SoVITS",
        PROJECT_ROOT.parent.parent / "GPT-SoVITS",
        PROJECT_ROOT.parent.parent / "github" / "GPT-SoVITS",
        Path.home() / "GPT-SoVITS",
        Path.home() / "Projects" / "github" / "GPT-SoVITS",
    ]
    for root in roots:
        if root:
            candidates.append(Path(root) / "tts_server.py")
    return candidates


def _resolve_server_script() -> Optional[Path]:
    """解析 tts_server.py 路径；找不到返回 None。"""
    for candidate in _server_script_candidates():
        if candidate.is_file():
            return candidate
    return None


def _resolve_python(script: Path) -> str:
    """解析拉起服务用的解释器：环境变量 → 常见 conda 环境 → 仓库内 venv → 当前解释器。

    tts_server.py 需要 torch 等依赖，通常只能用 GPT-SoVITS 专属的 conda 环境启动。
    """
    configured = os.environ.get("TTS_PYTHON")
    if configured and Path(configured).exists():
        return configured

    python_names = ("python.exe",) if os.name == "nt" else ("python3", "python")
    script_dir = Path(script).parent
    candidates = []
    conda_env = os.environ.get("TTS_CONDA_ENV") or DEFAULT_CONDA_ENV
    for name in python_names:
        candidates.append(Path.home() / ".conda" / "envs" / conda_env / name)
        candidates.append(script_dir / ".venv" / ("Scripts" if os.name == "nt" else "bin") / name)
        candidates.append(script_dir / "venv" / ("Scripts" if os.name == "nt" else "bin") / name)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return sys.executable


class TtsService:
    """GPT-SoVITS TTS 服务客户端（本机 HTTP，默认 127.0.0.1:9881）。"""

    def __init__(self, base_url: Optional[str] = None, *, timeout: float = 300.0,
                 autostart: bool = True, session: Optional[requests.Session] = None):
        """
        :param base_url: 服务地址；默认取环境变量 TTS_SERVER_URL，再回退 127.0.0.1:9881
        :param timeout: 合成请求的读取超时（秒）；GPU 推理可能较慢
        :param autostart: 服务未启动时是否自动拉起 tts_server.py（默认开启；脚本位置见
                          _server_script_candidates，可用 TTS_SERVER_SCRIPT 环境变量指定）
        :param session: 注入 requests.Session（单测用）
        """
        self.base_url = (base_url or os.environ.get("TTS_SERVER_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.autostart = autostart
        self._http = session if session is not None else requests.Session()

    # ---- 探活与信息 ----

    def health(self) -> Optional[dict]:
        """服务在跑返回 /health 的 dict，未启动返回 None。"""
        try:
            resp = self._http.get(f"{self.base_url}/health", timeout=2)
            return resp.json() if resp.status_code == 200 else None
        except (requests.RequestException, ValueError):
            return None

    def list_roles(self) -> list[dict]:
        """可用角色列表（每项含 name/version/note）。"""
        try:
            resp = self._http.get(f"{self.base_url}/roles", timeout=5)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"获取 TTS 角色列表失败（{self.base_url}）：{exc}") from exc
        if not isinstance(data, list):
            raise RuntimeError(f"TTS 角色列表格式异常：{data!r}")
        return data

    # ---- 合成 ----

    def synthesize(
        self,
        role: str,
        text: str,
        *,
        lang: str = "zh",
        speed: float = 1.0,
        seed: int = -1,
        save_to=None,
    ) -> Path:
        """合成语音，返回本机可用的 wav 路径。

        :param role: 角色名（GPT-SoVITS characters/*.yaml 中注册的名称）
        :param lang: zh/ja/en/ko/yue/auto
        :param save_to: 给定时把音频另存到该路径（返回该路径）；否则返回服务端 wav 路径
        :return: wav 文件 Path
        """
        text = (text or "").strip()
        if not text:
            raise ValueError("合成文本不能为空")
        if lang not in _ALLOWED_LANGS:
            raise ValueError(f"不支持的语言：{lang}（可选 {'、'.join(_ALLOWED_LANGS)}）")

        if self.health() is None:
            if not self.autostart:
                raise RuntimeError(
                    f"TTS 服务未启动（{self.base_url}）。请先运行 GPT-SoVITS 的 tts_server.py；"
                    "或设置 TTS_SERVER_SCRIPT/TTS_PYTHON 环境变量并开启 autostart 自动拉起。"
                )
            self.ensure_server()

        payload = {"role": role, "text": text, "lang": lang, "speed": speed, "seed": seed}
        try:
            resp = self._http.post(f"{self.base_url}/tts", json=payload,
                                   timeout=(5, self.timeout))
        except requests.RequestException as exc:
            raise RuntimeError(f"请求 TTS 服务失败（{self.base_url}）：{exc}") from exc
        if resp.status_code != 200:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise RuntimeError(f"TTS 合成失败（HTTP {resp.status_code}）：{detail}")

        if save_to is not None:
            target = Path(save_to)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(resp.content)
            return target

        wav_path = urllib.parse.unquote(resp.headers.get("X-Wav-Path", ""))
        if not wav_path:
            raise RuntimeError("TTS 服务未返回 wav 路径（X-Wav-Path 缺失）")
        return Path(wav_path)

    # ---- 可选：自动拉起服务 ----

    def ensure_server(self, wait_s: float = 90.0) -> None:
        """拉起 tts_server.py 并等待就绪（与 GPT-SoVITS 的 tts_client 行为一致）。

        脚本路径按 _server_script_candidates 解析（环境变量 TTS_SERVER_SCRIPT → 常见位置）；
        解释器按 _resolve_python 解析（TTS_PYTHON → conda 环境 → 仓库内 venv → 当前解释器）。
        服务进程以 DETACHED 方式启动，日志写入系统临时目录。
        """
        script = _resolve_server_script()
        if script is None:
            searched = "、".join(str(path) for path in _server_script_candidates()) or "（无候选）"
            raise RuntimeError(
                f"未找到 tts_server.py，无法自动拉起 TTS 服务。已查找：{searched}。"
                "请设置 TTS_SERVER_SCRIPT 环境变量指向 GPT-SoVITS 仓库的 tts_server.py。"
            )
        python = _resolve_python(script)
        url = urllib.parse.urlsplit(self.base_url)
        host = url.hostname or "127.0.0.1"
        port = url.port or 9881

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | \
                            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        logger.info("【TTS】自动拉起服务：%s %s -a %s -p %s", python, script, host, port)
        with open(_AUTOSTART_LOG, "ab") as log:
            log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} BiliTools 自动拉起 ===\n".encode("utf-8"))
            proc = subprocess.Popen(
                [python, str(script), "-a", host, "-p", str(port)],
                cwd=str(Path(script).parent),
                stdout=log,
                stderr=log,
                creationflags=creationflags,
            )

        deadline = time.time() + wait_s
        while time.time() < deadline:
            if self.health() is not None:
                logger.info("【TTS】服务已就绪：%s", self.base_url)
                return
            if proc.poll() is not None:
                # 并发拉起时另一个实例可能已占住端口，给健康检查留出时间
                for _ in range(10):
                    time.sleep(1)
                    if self.health() is not None:
                        return
                raise RuntimeError(f"TTS 服务启动失败（进程退出，端口可能被占用）。日志：{_AUTOSTART_LOG}")
            time.sleep(1)
        raise RuntimeError(f"等待 TTS 服务就绪超时（{wait_s:.0f} 秒）。日志：{_AUTOSTART_LOG}")

    def close(self) -> None:
        self._http.close()
