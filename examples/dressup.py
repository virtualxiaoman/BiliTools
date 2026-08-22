"""表情包、收藏集和装扮示例。"""

from src.services import DressupService, EmoteService, GarbService


def download_emotes() -> None:
    """查询并下载收藏表情包。"""
    service = EmoteService()
    packages = service.get_packages("10239,10238")
    print(f"表情包详情 {len(packages)} 个")

    # 动态表情优先下载 GIF；使用完整 text 作为文件名：
    results = service.download_packages("10239", use_full_name=True)
    print(f"表情包下载完成，共 {len(results)} 个文件")


def download_garb() -> None:
    """搜索并下载收藏集/主题装扮。"""
    service = GarbService()
    items = service.search_items("洛天依")
    print(f"搜索结果 {len(items)} 个")
    item = service.select_search_item("洛天依")
    print("选中：", item)

    # 默认下载封面、卡片图片和卡片视频。
    results = service.download_by_keyword("洛天依")
    print(f"收藏集/装扮下载完成，共 {len(results)} 个文件")


def search_and_download_dressup() -> None:
    """统一搜索表情包、收藏集和主题装扮，然后批量下载。"""
    service = DressupService()
    items = service.search("洛天依")
    for item in items:
        print(item.kind, item.display_name, item.as_dict())

    selected = [item.as_dict() for item in items[:2]]
    results = service.download_items(selected, threads=2, use_full_name=False)
    print(f"统一装扮下载完成，共 {len(results)} 个文件")


if __name__ == "__main__":
    # 默认只搜索，不自动下载。
    items = DressupService().search("洛天依")
    print(f"搜索结果 {len(items)} 个")
