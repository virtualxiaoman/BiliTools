# from src import VideoService
# from src.models import VideoQuality
#
# service = VideoService()
# # results = service.download("BV19z3G6WEii")
# # print(f"已下载：{results}")
# # results = service.download("BV1sq3V6yEd1")
# # # results = service.download_video_with_audio("BV1Q43w6QETb", quality=VideoQuality.P1080)
# # print(f"已下载：{results}")
# results = service.download_fav(1186417978, mode="audio")
# # print(f"已下载：{results}")
# # from pprint import pprint
# #
# # from src import ArchiveService, UserService
# #
# # # # ans = ArchiveService().list_seasons(mid=506925078)
# # # # pprint(ans)
# # # ans = ArchiveService().get_sidlist_by_mid(mid=506925078)
# # # print(len(ans))
# # # print(ans)
# #
# # print(UserService().fetch_info(mid=506925078))

# from src.services import EmoteService
#
# # 默认：使用简称
# EmoteService().download_packages("10239,10238")

# from src.services import ReplyService
# from pprint import pprint
# comments = ReplyService().get_comments(bvid="BV1ov42117yC", sort="hot", max_count=10)
# pprint(comments)
# from src.services import ReplyService
#
# service = ReplyService()
#
# comments = service.get_dynamic_comments("https://www.bilibili.com/opus/1151100571637252104", sort="hot", max_count=20)
# print(comments)
# #
# from src.services import VideoService
# from src.services import LoginService
#
# login = LoginService()
#
# user = login.get_login_state()
# print(user.is_login, user.mid, user.uname, user.face, user.level)
# service = VideoService()
#
# result = service.fetch_ai_summary(bvid="BV1ov42117yC")
#
# print(result.summary_text)
# print(result.model_result.summary)
# print(result.model_result.outline)
# print(result.model_result.subtitle)
# from src import VideoService
#
# service = VideoService()
#
# result = service.download_danmaku("BV1ov42117yC")
# print(result.path)
# result = service.download_video_with_audio("BV1ov42117yC")
# print(result.path)
from src.services import DynamicService

service = DynamicService()
# service.download_user_dynamics(36081646)                        # 全部动态
# service.download_user_dynamics(36081646, max_count=20)          # 最新 20 条
service.download_user_dynamics(36081646)
