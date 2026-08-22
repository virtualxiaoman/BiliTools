"""UP 主投稿查询和下载示例。"""

from src.services import VideoService


MID = 249056021


def list_up_videos() -> None:
    """查询 UP 主投稿列表。"""
    service = VideoService()
    bvids = service.list_up_videos(MID)
    print(f"UP主共 {len(bvids)} 个视频：")
    print(bvids)


def download_up_videos() -> None:
    """下载 UP 主全部投稿，或改为只下载音频。"""
    service = VideoService()

    # 下载全部视频（含音频合成）：
    # results = service.download_up(MID)

    # 仅下载音频：
    results = service.download_up(MID, mode="audio")
    print(f"UP主下载完成，共 {len(results)} 个文件")
    for result in results:
        print("  ", result.path.name)


if __name__ == "__main__":
    list_up_videos()
