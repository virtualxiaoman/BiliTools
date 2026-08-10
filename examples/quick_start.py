# BiliTools 使用示例
"""
示例代码均以视频 BV1ov42117yC 为例。
up主：蔚蓝档案。标题：动画小剧场《补习部的一天》第4集：烟火

运行方式：从项目根目录执行 `python -m examples.quick_start`
"""

from pathlib import Path

from src.models import VideoQuality
from src.services import (
    ArchiveService,
    FavService,
    HistoryService,
    LoginService,
    MessageService,
    RankService,
    ReplyService,
    UserService,
    VideoService,
)


def login_qr():
    """扫码登录，登录成功后 cookie 保存到 assets/cookie/qr_login.txt。"""
    service = LoginService()
    success = service.qr_login()  # 阻塞轮询，默认 60s 超时
    print(f"登录结果：{success}")


def get_video_info():
    """获取视频信息。"""
    service = VideoService()
    info = service.fetch_info_with_tags("BV1ov42117yC")
    print(f"标题：{info.title}")
    print(f"UP主：{info.owner.name}（mid={info.owner.mid}）")
    print(f"播放/弹幕/评论：{info.stat.num_view}/{info.stat.num_dm}/{info.stat.num_reply}")
    print(f"标签：{info.tags}")


def download_video():
    """下载视频到 output/video/，文件名自动为 [标题](BV号).mp4。

    默认最高清晰度(4K)。指定 quality 时精确匹配该档位，匹配不到回退到最高可用。
    """
    service = VideoService()
    result = service.download_video_with_audio(
        "BV1ov42117yC",
        # 不传 quality 默认 4K；传 P1080 则精确下载 1080P（有 4K 也不会被拉高）
        # quality=VideoQuality.P1080,
    )
    print(f"已下载：{result.path}")


def download_cover():
    """下载封面。"""
    service = VideoService()
    result = service.download_cover("BV1ov42117yC")
    print(f"封面：{result.path}")


def get_user_info():
    """获取 UP 主信息。"""
    service = UserService()
    info = service.fetch_info(3493265644980448)  # 蔚蓝档案官方
    print(f"昵称：{info.name}，粉丝：{info.num_follower}，等级：{info.level}")


def get_rank():
    """获取热门视频列表。"""
    service = RankService()
    bvs = service.get_popular(pn=1, ps=10)
    print(f"热门视频 {len(bvs)} 个：{bvs[:3]}...")


def get_history():
    """获取历史记录并导出 xlsx。"""
    service = HistoryService()
    items = service.get_history_all(max_iter=2, ps=10)
    service.save_video_history_df(items, save_name="history")
    print(f"历史记录 {len(items)} 条已导出")


def get_fav():
    """获取收藏夹视频。"""
    service = FavService()
    bvs = service.get_fav_bv(827560778)  # 默认收藏夹 media_id 示例
    print(f"收藏夹视频 {len(bvs)} 个")


def get_archive():
    """获取视频合集视频。"""
    service = ArchiveService()
    bvs = service.get_archives_list(1717000, mid=506925078)  # 合集·明日方舟
    print(f"合集视频 {len(bvs)} 个")


def download_fav():
    """下载收藏夹全部视频（有声音）或仅音频（缓存听歌）。

    URL 或 media_id 均可；保存到 output/video/<收藏夹名>/。
    """
    service = VideoService()
    fav_url = "https://space.bilibili.com/506925078/favlist?fid=3953119978&ftype=create"
    # 下载全部视频（含音频合成）
    # results = service.download_fav(fav_url)
    # 仅下载音频（本地缓存听歌）
    results = service.download_fav(fav_url, mode="audio")
    print(f"收藏夹下载完成，共 {len(results)} 个文件")
    for r in results:
        print("  ", r.path.name)


def download_up():
    """下载某 UP 主空间全部视频（有声音）或仅音频。

    URL 或 mid 均可；保存到 output/video/<UP主昵称>/。
    """
    service = VideoService()
    up_url = "https://space.bilibili.com/249056021"
    # 先查看 UP 主的视频列表
    bvs = service.list_up_videos(up_url)
    print(f"UP主共 {len(bvs)} 个视频：{bvs}")
    # 下载全部视频（含音频合成）
    # results = service.download_up(up_url)
    # 仅下载音频
    results = service.download_up(up_url, mode="audio")
    print(f"UP主下载完成，共 {len(results)} 个文件")
    for r in results:
        print("  ", r.path.name)


def download_multi_page():
    """下载多P视频的指定分P（BV1Q43w6QETb 是 9 分P视频，含音频）。"""
    service = VideoService()
    # 指定第 2 个分P：文件名形如 [标题]-P02-[part](BV号).mp4
    result = service.download_video_with_audio("BV1Q43w6QETb", page=2, quality=VideoQuality.P1080)
    print(f"分P下载：{result.path}")
    # 下载全部分P
    # results = service.download_all_pages("BV1Q43w6QETb", quality=VideoQuality.P1080)
    # print(f"已下载 {len(results)} 个分P")


def download_season():
    """下载整个合集。bvid 与 sid 任选其一。"""
    service = VideoService()
    # 方式1：从合集内任意一个视频进入
    # results = service.download_season("BV1Q43w6QETb", quality=VideoQuality.P1080)
    # 方式2：按 sid 直接下载（洛天依·纯蓝幻乐 / 他人合集 明日方舟）
    # results = service.download_season(season_id=8683221, quality=VideoQuality.P1080)
    # results = service.download_season(season_id=1717000, mid=506925078, quality=VideoQuality.P1080)
    # 先查看合集结构
    season = service.fetch_season(season_id=8683221)
    print(f"合集「{season.title}」共 {len(season.episodes)} 个稿件")
    # results = service.download_season(season_id=season.id, quality=VideoQuality.P1080)
    # print(f"合集下载完成，共 {len(results)} 个文件")


def unified_download():
    """统一下载入口：只传 bvid，自动决定范围（合集/单视频）+ 最高清晰度 + 进度显示。"""
    service = VideoService()
    results = service.download("BV1ov42117yC")  # 单视频
    # results = service.download("BV1Q43w6QETb")  # 属于合集 → 下载整个合集
    print(f"下载完成，共 {len(results)} 个文件")
    for r in results:
        print("  ", r.path.name)


def send_reply():
    """发表评论（注意：会真实发布，谨慎运行）。"""
    service = ReplyService()
    rpid = service.send_reply("小梓我喜欢你~", bvid="BV1ov42117yC")
    print(f"评论成功，rpid={rpid}")


def send_message():
    """发送私信（注意：会真实发送，谨慎运行）。"""
    service = MessageService()
    service.send_msg(receiver_uid=3493133776062465, content="你好，请问是千年的爱丽丝同学吗？")
    print("私信已发送")


if __name__ == "__main__":
    # 依次取消注释运行
    # login_qr()
    get_video_info()
    # download_video()
    # download_cover()
    # get_user_info()
    # get_rank()
    # get_history()
    # get_fav()
    # get_archive()
    # download_fav()
    # download_up()
    # download_multi_page()
    # download_season()
    # unified_download()
    # send_reply()
    # send_message()
    pass
