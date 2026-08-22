"""收藏夹查询和下载示例。"""

from src.services import FavService, VideoService


# 保留两个常用示例：查询示例来自原 quick_start.py，下载示例使用另一个收藏夹。
QUERY_MEDIA_ID = 827560778
DOWNLOAD_MEDIA_ID = 3953119978


def get_favorite() -> None:
    """获取收藏夹详情和 BV 列表。"""
    service = FavService()
    info = service.get_fav_info(QUERY_MEDIA_ID)
    bvids = service.get_fav_bv(QUERY_MEDIA_ID)
    print(f"收藏夹：{info.title}")
    print(f"视频数量：{len(bvids)}")
    print(bvids[:10])


def download_favorite() -> None:
    """下载收藏夹视频，或改为只下载音频。"""
    service = VideoService()

    # 下载全部视频（含音频合成）：
    # results = service.download_fav(DOWNLOAD_MEDIA_ID)

    # 仅下载音频，保存到 output/video/<收藏夹名>/：
    results = service.download_fav(DOWNLOAD_MEDIA_ID, mode="audio")
    print(f"收藏夹下载完成，共 {len(results)} 个文件")
    for result in results:
        print("  ", result.path.name)


if __name__ == "__main__":
    # 默认只查询，不执行批量下载。
    get_favorite()
