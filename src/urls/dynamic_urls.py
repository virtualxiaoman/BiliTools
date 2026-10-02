"""
动态（opus）相关的接口 URL。
"""

from src.config.constants import API_BASE


class DynamicUrls:
    """动态接口。"""

    DETAIL = f"{API_BASE}/x/polymer/web-dynamic/v1/detail"  # 单条动态完整结构
    OPUS_DETAIL = f"{API_BASE}/x/polymer/web-dynamic/v1/opus/detail"  # 长文/专栏全文（段落化）
    SPACE_FEED = f"{API_BASE}/x/polymer/web-dynamic/v1/feed/space"  # UP 主空间动态列表（需 wbi）

    # detail 接口必须携带的 features。缺失时接口返回老式表示（major.draw），
    # 正文（summary）与附加卡片会直接丢失，因此所有 detail 请求都要带上。
    DETAIL_FEATURES = "itemOpusStyle,listOnlyfans,opusBigCover,onlyfansVote"
