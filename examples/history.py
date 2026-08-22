"""历史记录查询和导出示例。"""

from src.services import HistoryService


def export_history() -> None:
    """获取历史记录并导出到 output/history/history.xlsx。"""
    service = HistoryService()
    items = service.get_history_all(max_iter=2, ps=10)
    service.save_video_history_df(items, save_name="history")
    print(f"历史记录 {len(items)} 条已导出")


def find_invalid_videos() -> None:
    """查找已经失效的视频。"""
    items = HistoryService().get_invalid_video(["BV1sS411w7Fk", "BV1aM4m127Ab"])
    print(f"失效视频数量：{len(items)}")
    print(items)


if __name__ == "__main__":
    export_history()
