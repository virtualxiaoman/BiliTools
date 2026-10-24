from src.services import ReplyService

result = ReplyService().export_video_comments(
    bvid="BV1A99yBYE6p",
    sort="latest",  # latest / hot
    max_count=-1,  # 根评论上限，-1 全部
    with_sub_replies=True,  # 抓取全部楼中楼
)
print(result.export_dir)
print(result.root_count, result.sub_count, result.pinned_count)
