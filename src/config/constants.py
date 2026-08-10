"""
静态常量：基础域名、User-Agent、重试参数等。

原 `src/config.py` 中 `Config` 类的静态部分迁到这里。
"""

# ---- 基础域名 ----
API_BASE = "https://api.bilibili.com"
PASSPORT_BASE = "https://passport.bilibili.com"
API_VC_BASE = "https://api.vc.bilibili.com"
WEB_BASE = "https://www.bilibili.com"
SPACE_BASE = "https://space.bilibili.com"
MESSAGE_BASE = "https://message.bilibili.com"

# ---- 请求头 ----
class UserAgent:
    def __init__(self):
        # self.pcChrome = """Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"""
        self.pcChrome = """Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"""


# ---- 重试参数（原 Config.MAX_RETRY / RETRY_DELAY） ----
MAX_RETRY = 3  # 最大重试次数
RETRY_DELAY = 0.712  # 重试延迟（秒）

# ---- 下载参数 ----
# fnval 置为 4048 会取到所有可用 DASH 视频流；见 BAC 文档 videostream_url
DASH_FNVAL = 4048
# 默认请求超时（秒）
REQUEST_TIMEOUT = 15
