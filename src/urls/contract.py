"""
契约（老粉）相关的接口 URL。
原 `src/up.py` 中的签约接口迁移至此。
"""

from src.config.constants import API_BASE


class ContractUrls:
    """老粉/契约接口。"""

    ADD_CONTRACT = f"{API_BASE}/x/v1/contract/add_contract"  # 成为UP主老粉（签约）
