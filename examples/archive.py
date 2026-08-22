"""合集查询和下载示例。"""

from src.services import ArchiveService, VideoService


SEASON_ID = 1717000
MID = 506925078


def get_archive() -> None:
    """查询用户的合集列表、合集详情和 BV 列表。"""
    service = ArchiveService()
    print("合集 sid 列表：", service.get_sidlist_by_mid(MID))
    season_data = service.get_season_by_sid(SEASON_ID, mid=MID)
    print("合集元信息：", season_data.get("meta"))
    print("合集 BV 列表：", service.get_bvlist_by_sid(SEASON_ID, mid=MID))


def download_archive() -> None:
    """下载整个合集。"""
    service = VideoService()
    # 方式1：从合集内任意一个视频进入。
    # results = service.download_season("BV1Q43w6QETb")

    # 方式2：直接传 sid；他人合集通常还需要传 mid。
    results = service.download_season(season_id=SEASON_ID, mid=MID)
    print(f"合集下载完成，共 {len(results)} 个文件")


if __name__ == "__main__":
    get_archive()
