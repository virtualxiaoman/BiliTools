"""
评论相关的接口 URL。
原 `src/reply.py` 中的评论接口迁移至此。
"""

from src.config.constants import API_BASE


class CommentUrls:
    """评论接口。"""

    ADD = f"{API_BASE}/x/v2/reply/add"  # 发表评论
    LIST = f"{API_BASE}/x/v2/reply"  # 评论列表（爬取评论用，暂未实现）
