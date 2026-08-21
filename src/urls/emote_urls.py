"""表情包相关的接口 URL。"""

from src.config.constants import API_BASE


class EmoteUrls:
    """B 站表情包接口。"""

    PACKAGE = f"{API_BASE}/x/emote/package"
    SEARCH = f"{API_BASE}/x/emote/package/search"
