"""视频信息和下载示例。

从项目根目录执行：

    python -m examples.video

本文件按功能拆分了原 quick_start.py 中的视频相关示例；修改 main() 中的调用即可切换示例。
"""

from src.models import VideoQuality
from src.services import VideoService


BVID = "BV1ov42117yC"
MULTI_PAGE_BVID = "BV1Q43w6QETb"


def get_video_info() -> None:
    """获取视频信息和标签，不下载媒体文件。"""
    service = VideoService()
    info = service.fetch_info_with_tags(BVID)
    print(f"标题：{info.title}")
    print(f"UP主：{info.owner.name}（mid={info.owner.mid}）")
    print(f"播放/弹幕/评论：{info.stat.num_view}/{info.stat.num_dm}/{info.stat.num_reply}")
    print(f"标签：{info.tags}")
    print(f"分P数量：{len(info.pages)}")


def download_video() -> None:
    """下载视频和音频并合成为 mp4。"""
    result = VideoService().download_video_with_audio(
        BVID,
        # 不传 quality 默认优先 4K；没有对应档位时回退到最高可用清晰度。
        # quality=VideoQuality.P1080,
    )
    print(f"已下载：{result.path}，缓存命中：{result.cached}")


def download_cover() -> None:
    """只下载视频封面。"""
    result = VideoService().download_cover(BVID)
    print(f"封面：{result.path}")


def download_multi_page() -> None:
    """下载多P视频的指定分P或全部分P。"""
    service = VideoService()
    # 指定第 2 个分P：文件名包含 P 序号。
    result = service.download_video_with_audio(
        MULTI_PAGE_BVID,
        page=2,
        quality=VideoQuality.P1080,
    )
    print(f"第 2P 下载完成：{result.path}")

    # 需要全部分P时可以使用下面的调用：
    # results = service.download_all_pages(MULTI_PAGE_BVID, quality=VideoQuality.P1080)
    # print(f"全部分P下载完成，共 {len(results)} 个文件")


def download_season() -> None:
    """通过 BV 号或 sid 查看并下载合集。"""
    service = VideoService()

    # 先查看合集结构。
    season = service.fetch_season(season_id=8683221)
    print(f"合集「{season.title}」共 {len(season.episodes)} 个稿件")

    # 合集下载示例：
    # results = service.download_season(MULTI_PAGE_BVID, quality=VideoQuality.P1080)
    # results = service.download_season(season_id=8683221, quality=VideoQuality.P1080)
    # results = service.download_season(season_id=1717000, mid=506925078, quality=VideoQuality.P1080)
    # print(f"合集下载完成，共 {len(results)} 个文件")


def unified_download() -> None:
    """自动判断下载范围：普通视频下载全部分P，合集视频下载整个合集。"""
    results = VideoService().download(BVID)
    print(f"统一下载完成，共 {len(results)} 个文件")
    for result in results:
        print("  ", result.path.name)


if __name__ == "__main__":
    # 默认只执行一个信息查询，避免用户运行示例时意外开始下载。
    get_video_info()
