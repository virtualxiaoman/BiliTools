"""热门、排行榜和新视频示例。"""

from src.services import RankService


def get_rank() -> None:
    service = RankService()
    popular = service.get_popular(pn=1, ps=10)
    ranking = service.get_ranking()
    new_videos = service.get_new(rid=1, pn=1, ps=5)
    print(f"热门视频 {len(popular)} 个：{popular[:3]}...")
    print(f"排行榜视频 {len(ranking)} 个：{ranking[:3]}...")
    print(f"新视频 {len(new_videos)} 个：{new_videos[:3]}...")


if __name__ == "__main__":
    get_rank()
