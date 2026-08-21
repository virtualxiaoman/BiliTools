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

from src.services import EmoteService

# 默认：使用简称
EmoteService().download_packages("10239,10238")
