"""B 站收藏集与装扮商城接口 URL。"""

from src.config.constants import API_BASE


class GarbUrls:
    """装扮商城、收藏集（DLC）相关接口。"""

    SEARCH = f"{API_BASE}/x/garb/v2/mall/home/search"
    SUIT_DETAIL = f"{API_BASE}/x/garb/v2/mall/suit/detail"
    COLLECTION_DETAIL = f"{API_BASE}/x/vas/dlc_act/lottery_home_detail"
