"""
pytest 公共配置。

- 确保项目根目录在 sys.path（运行 `pytest` 时能 import src）；
- 注册 `network` 标记（真实网络测试，默认跳过，加 -m network 运行）；
- 提供共享 fixture：默认 cookie 的 BiliSession。
"""

import os
import sys

import pytest

# 确保项目根目录可导入（运行 pytest 时自动处理）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 网络测试默认跳过：`pytest -m "not network"` 只跑单元测试；
# `pytest -m network` 或 `pytest` 跑全部（含真实网络，需可访问 B 站）。
NETWORK_REQUIRED = os.environ.get("BILITOOLS_NETWORK", "") == "1"


def pytest_addoption(parser):
    parser.addoption(
        "--network",
        action="store_true",
        default=False,
        help="运行真实网络测试（默认跳过）",
    )


def pytest_collection_modifyitems(config, items):
    run_network = config.getoption("--network") or NETWORK_REQUIRED
    skip_marker = pytest.mark.skip(reason="网络测试，需要 --network 或 BILITOOLS_NETWORK=1")
    for item in items:
        if "network" in item.keywords and not run_network:
            item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def session():
    """共享 BiliSession（使用默认 cookie）。"""
    from src.api import BiliSession
    return BiliSession()


@pytest.fixture(scope="session")
def video_service():
    """共享 VideoService。"""
    from src.services import VideoService
    return VideoService()
