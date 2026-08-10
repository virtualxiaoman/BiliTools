import src.video
from video import BiliVideo
from src.config import BiliCookies as cookies
from src.config import UserAgent
from src.utils import BiliVideoUtil, BV2AV
import requests
# a = BV2AV().bv2av("BV1Gp4y1k7YT")
# print(a)
#
# # 对https://api.bilibili.com/x/web-interface/archive/stat发get请求
# # 请求参数是bvid="BV1Gp4y1k7YT"
#
# headers = {
#     "User-Agent": useragent().pcChrome,
#     "Cookie": cookies().bilicookie,
#     'referer': "https://www.bilibili.com"
# }
# r = requests.get("https://api.bilibili.com/x/web-interface/view", params={"bvid": "BV1ov42117yC"}, headers=headers)
#
# print(r.json())
# 似乎可以用其中的ugc_season获取合集
# {'code': 0, 'message': '0', 'ttl': 1, 'data': {'bvid': 'BV1ov42117yC', 'aid': 1450404511, 'videos': 1, 'tid': 27, 'tname': '综合', 'copyright': 1, 'pic': 'http://i2.hdslb.com/bfs/archive/bc29b9ce56e626786f28bf11eaf71e4be1bae388.jpg', 'title': '动画小剧场《补习部的一天》第4集：烟火', 'pubdate': 1707447600, 'ctime': 1707104101, 'desc': '动画小剧场《补习部的一天》现已更新！\n《补习部的一天》第4集：烟火\n\n除了学习以外，补习部的成员们平常都在做些什么呢？今天刚好工作闲下来，老师快去关心关心她们吧！\t\n不管是学习还是生活，梓现在都已经更加适应了。她也在用自己的方式，默默地关心保护着补习部和老师。\t\n不过如果她能够稍微放松一些......应该就更好了吧？\n\n点击链接即可前往bilibili游戏中心下载：https://www.biligame.com/detail/?id=109864\n相关更多游戏内容详见后续《蔚蓝档案》官方账号及游戏内、官网公告资讯推送！', 'desc_v2': [{'raw_text': '动画小剧场《补习部的一天》现已更新！\n《补习部的一天》第4集：烟火\n\n除了学习以外，补习部的成员们平常都在做些什么呢？今天刚好工作闲下来，老师快去关心关心她们吧！\t\n不管是学习还是生活，梓现在都已经更加适应了。她也在用自己的方式，默默地关心保护着补习部和老师。\t\n不过如果她能够稍微放松一些......应该就更好了吧？\n\n点击链接即可前往bilibili游戏中心下载：https://www.biligame.com/detail/?id=109864\n相关更多游戏内容详见后续《蔚蓝档案》官方账号及游戏内、官网公告资讯推送！', 'type': 1, 'biz_id': 0}], 'state': 0, 'duration': 219, 'rights': {'bp': 0, 'elec': 0, 'download': 1, 'movie': 0, 'pay': 0, 'hd5': 1, 'no_reprint': 1, 'autoplay': 1, 'ugc_pay': 0, 'is_cooperation': 0, 'ugc_pay_preview': 0, 'no_background': 0, 'clean_mode': 0, 'is_stein_gate': 0, 'is_360': 0, 'no_share': 0, 'arc_pay': 0, 'free_watch': 0}, 'owner': {'mid': 3493265644980448, 'name': '蔚蓝档案', 'face': 'https://i1.hdslb.com/bfs/face/f2635e09fe667d4ad29229c6ed0b5f4bdea09bd1.jpg'}, 'stat': {'aid': 1450404511, 'view': 514092, 'danmaku': 3396, 'reply': 1589, 'favorite': 15617, 'coin': 21972, 'share': 6010, 'now_rank': 0, 'his_rank': 0, 'like': 49305, 'dislike': 0, 'evaluation': '', 'vt': 0}, 'argue_info': {'argue_msg': '', 'argue_type': 0, 'argue_link': ''}, 'dynamic': '#蔚蓝档案# #蔚蓝档案半周年#\n动画小剧场《补习部的一天》现已更新！\n《补习部的一天》第4集：烟火', 'cid': 1430654778, 'dimension': {'width': 1920, 'height': 1080, 'rotate': 0}, 'season_id': 2086865, 'premiere': None, 'teenage_mode': 0, 'is_chargeable_season': False, 'is_story': False, 'is_upower_exclusive': False, 'is_upower_play': False, 'is_upower_preview': False, 'enable_vt': 0, 'vt_display': '', 'no_cache': False, 'pages': [{'cid': 1430654778, 'page': 1, 'from': 'vupload', 'part': '动画小剧场《补习部的一天》第4集：烟火', 'duration': 219, 'vid': '', 'weblink': '', 'dimension': {'width': 1920, 'height': 1080, 'rotate': 0}, 'first_frame': 'http://i0.hdslb.com/bfs/storyff/n240205sa3qijkv0op0mn1fvtubvymnm_firsti.jpg'}], 'subtitle': {'allow_submit': False, 'list': [{'id': 1417284446083901440, 'lan': 'ai-zh', 'lan_doc': '中文（自动生成）', 'is_lock': False, 'subtitle_url': '', 'type': 1, 'id_str': '1417284446083901440', 'ai_type': 0, 'ai_status': 2, 'author': {'mid': 0, 'name': '', 'sex': '', 'face': '', 'sign': '', 'rank': 0, 'birthday': 0, 'is_fake_account': 0, 'is_deleted': 0, 'in_reg_audit': 0, 'is_senior_member': 0, 'name_render': None}}]}, 'ugc_season': {'id': 2086865, 'title': '补习部的一天', 'cover': 'https://archive.biliimg.com/bfs/archive/2fe1086f34f8884546fc152dfe85ec024f127428.png', 'mid': 3493265644980448, 'intro': '', 'sign_state': 0, 'attribute': 140, 'sections': [{'season_id': 2086865, 'id': 2394423, 'title': '正片', 'type': 1, 'episodes': [{'season_id': 2086865, 'section_id': 2394423, 'id': 50006776, 'aid': 751478363, 'cid': 1410994885, 'title': '动画小剧场《补习部的一天》第1集：你来这里干什么', 'attribute': 0, 'arc': {'aid': 751478363, 'videos': 0, 'type_id': 0, 'type_name': '', 'copyright': 0, 'pic': 'http://i2.hdslb.com/bfs/archive/19a14e32b76015d3afc7dcf9268899d0f48e105a.jpg', 'title': '动画小剧场《补习部的一天》第1集：你来这里干什么', 'pubdate': 1705633200, 'ctime': 1705633200, 'desc': '', 'state': 0, 'duration': 224, 'rights': {'bp': 0, 'elec': 0, 'download': 0, 'movie': 0, 'pay': 0, 'hd5': 0, 'no_reprint': 0, 'autoplay': 0, 'ugc_pay': 0, 'is_cooperation': 0, 'ugc_pay_preview': 0, 'arc_pay': 0, 'free_watch': 0}, 'author': {'mid': 0, 'name': '', 'face': ''}, 'stat': {'aid': 751478363, 'view': 1118573, 'danmaku': 4100, 'reply': 3001, 'fav': 39475, 'coin': 32247, 'share': 16552, 'now_rank': 0, 'his_rank': 0, 'like': 80197, 'dislike': 0, 'evaluation': '', 'argue_msg': '', 'vt': 0, 'vv': 1118573}, 'dynamic': '', 'dimension': {'width': 0, 'height': 0, 'rotate': 0}, 'desc_v2': None, 'is_chargeable_season': False, 'is_blooper': False, 'enable_vt': 0, 'vt_display': ''}, 'page': {'cid': 1410994885, 'page': 1, 'from': 'vupload', 'part': '动画小剧场《补习部的一天》第1集：你来这里干什么', 'duration': 224, 'vid': '', 'weblink': '', 'dimension': {'width': 1920, 'height': 1080, 'rotate': 0}}, 'bvid': 'BV1tk4y1D7Dw'}, {'season_id': 2086865, 'section_id': 2394423, 'id': 50688436, 'aid': 879209648, 'cid': 1418797724, 'title': '动画小剧场《补习部的一天》第2集：天马行空的少女', 'attribute': 0, 'arc': {'aid': 879209648, 'videos': 0, 'type_id': 0, 'type_name': '', 'copyright': 0, 'pic': 'http://i0.hdslb.com/bfs/archive/8b3d5272f85226c8479c920845b34a018997ca19.jpg', 'title': '动画小剧场《补习部的一天》第2集：天马行空的少女', 'pubdate': 1706238000, 'ctime': 1706238000, 'desc': '', 'state': 0, 'duration': 219, 'rights': {'bp': 0, 'elec': 0, 'download': 0, 'movie': 0, 'pay': 0, 'hd5': 0, 'no_reprint': 0, 'autoplay': 0, 'ugc_pay': 0, 'is_cooperation': 0, 'ugc_pay_preview': 0, 'arc_pay': 0, 'free_watch': 0}, 'author': {'mid': 0, 'name': '', 'face': ''}, 'stat': {'aid': 879209648, 'view': 1019613, 'danmaku': 3614, 'reply': 2152, 'fav': 46683, 'coin': 21441, 'share': 13323, 'now_rank': 0, 'his_rank': 0, 'like': 61808, 'dislike': 0, 'evaluation': '', 'argue_msg': '', 'vt': 0, 'vv': 1019613}, 'dynamic': '', 'dimension': {'width': 0, 'height': 0, 'rotate': 0}, 'desc_v2': None, 'is_chargeable_season': False, 'is_blooper': False, 'enable_vt': 0, 'vt_display': ''}, 'page': {'cid': 1418797724, 'page': 1, 'from': 'vupload', 'part': '动画小剧场《补习部的一天》第2集：天马行空的少女', 'duration': 219, 'vid': '', 'weblink': '', 'dimension': {'width': 1920, 'height': 1080, 'rotate': 0}}, 'bvid': 'BV1rN4y1H7zo'}, {'season_id': 2086865, 'section_id': 2394423, 'id': 51255087, 'aid': 1000232081, 'cid': 1426738118, 'title': '动画小剧场《补习部的一天》第3集：热情的助眠', 'attribute': 0, 'arc': {'aid': 1000232081, 'videos': 0, 'type_id': 0, 'type_name': '', 'copyright': 0, 'pic': 'http://i1.hdslb.com/bfs/archive/20c4f7a1d0c5bc946e7fe5c226252c4cfac65499.jpg', 'title': '动画小剧场《补习部的一天》第3集：热情的助眠', 'pubdate': 1706842800, 'ctime': 1706842800, 'desc': '', 'state': 0, 'duration': 230, 'rights': {'bp': 0, 'elec': 0, 'download': 0, 'movie': 0, 'pay': 0, 'hd5': 0, 'no_reprint': 0, 'autoplay': 0, 'ugc_pay': 0, 'is_cooperation': 0, 'ugc_pay_preview': 0, 'arc_pay': 0, 'free_watch': 0}, 'author': {'mid': 0, 'name': '', 'face': ''}, 'stat': {'aid': 1000232081, 'view': 462531, 'danmaku': 2314, 'reply': 1098, 'fav': 10981, 'coin': 12824, 'share': 3590, 'now_rank': 0, 'his_rank': 0, 'like': 37720, 'dislike': 0, 'evaluation': '', 'argue_msg': '', 'vt': 0, 'vv': 462531}, 'dynamic': '', 'dimension': {'width': 0, 'height': 0, 'rotate': 0}, 'desc_v2': None, 'is_chargeable_season': False, 'is_blooper': False, 'enable_vt': 0, 'vt_display': ''}, 'page': {'cid': 1426738118, 'page': 1, 'from': 'vupload', 'part': '动画小剧场《补习部的一天》第3集：热情的助眠', 'duration': 230, 'vid': '', 'weblink': '', 'dimension': {'width': 1920, 'height': 1080, 'rotate': 0}}, 'bvid': 'BV1Qx4y1Z7ng'}, {'season_id': 2086865, 'section_id': 2394423, 'id': 51672889, 'aid': 1450404511, 'cid': 1430654778, 'title': '动画小剧场《补习部的一天》第4集：烟火', 'attribute': 0, 'arc': {'aid': 1450404511, 'videos': 0, 'type_id': 0, 'type_name': '', 'copyright': 0, 'pic': 'http://i2.hdslb.com/bfs/archive/bc29b9ce56e626786f28bf11eaf71e4be1bae388.jpg', 'title': '动画小剧场《补习部的一天》第4集：烟火', 'pubdate': 1707447600, 'ctime': 1707447600, 'desc': '', 'state': 0, 'duration': 219, 'rights': {'bp': 0, 'elec': 0, 'download': 0, 'movie': 0, 'pay': 0, 'hd5': 0, 'no_reprint': 0, 'autoplay': 0, 'ugc_pay': 0, 'is_cooperation': 0, 'ugc_pay_preview': 0, 'arc_pay': 0, 'free_watch': 0}, 'author': {'mid': 0, 'name': '', 'face': ''}, 'stat': {'aid': 1450404511, 'view': 514092, 'danmaku': 3396, 'reply': 1589, 'fav': 15617, 'coin': 21972, 'share': 6010, 'now_rank': 0, 'his_rank': 0, 'like': 49305, 'dislike': 0, 'evaluation': '', 'argue_msg': '', 'vt': 0, 'vv': 514092}, 'dynamic': '', 'dimension': {'width': 0, 'height': 0, 'rotate': 0}, 'desc_v2': None, 'is_chargeable_season': False, 'is_blooper': False, 'enable_vt': 0, 'vt_display': ''}, 'page': {'cid': 1430654778, 'page': 1, 'from': 'vupload', 'part': '动画小剧场《补习部的一天》第4集：烟火', 'duration': 219, 'vid': '', 'weblink': '', 'dimension': {'width': 1920, 'height': 1080, 'rotate': 0}}, 'bvid': 'BV1ov42117yC'}, {'season_id': 2086865, 'section_id': 2394423, 'id': 52109975, 'aid': 1100411329, 'cid': 1434983799, 'title': '动画小剧场《补习部的一天》第5集：锻炼的姿势也很重要哦', 'attribute': 2, 'arc': {'aid': 1100411329, 'videos': 0, 'type_id': 0, 'type_name': '', 'copyright': 0, 'pic': 'http://i0.hdslb.com/bfs/archive/a51e3349b267a3c7dec196dd5643a76689eb33e5.jpg', 'title': '动画小剧场《补习部的一天》第5集：锻炼的姿势也很重要哦', 'pubdate': 1707534000, 'ctime': 1707534000, 'desc': '', 'state': 0, 'duration': 358, 'rights': {'bp': 0, 'elec': 0, 'download': 0, 'movie': 0, 'pay': 0, 'hd5': 0, 'no_reprint': 0, 'autoplay': 0, 'ugc_pay': 0, 'is_cooperation': 0, 'ugc_pay_preview': 0, 'arc_pay': 0, 'free_watch': 0}, 'author': {'mid': 0, 'name': '', 'face': ''}, 'stat': {'aid': 1100411329, 'view': 681898, 'danmaku': 4811, 'reply': 1706, 'fav': 26638, 'coin': 24871, 'share': 7313, 'now_rank': 0, 'his_rank': 0, 'like': 54157, 'dislike': 0, 'evaluation': '', 'argue_msg': '', 'vt': 0, 'vv': 681898}, 'dynamic': '', 'dimension': {'width': 0, 'height': 0, 'rotate': 0}, 'desc_v2': None, 'is_chargeable_season': False, 'is_blooper': False, 'enable_vt': 0, 'vt_display': ''}, 'page': {'cid': 1434983799, 'page': 1, 'from': 'vupload', 'part': '动画小剧场《补习部的一天》第5集：锻炼的姿势也很重要哦', 'duration': 358, 'vid': '', 'weblink': '', 'dimension': {'width': 1920, 'height': 1080, 'rotate': 0}}, 'bvid': 'BV18A4m157b5'}]}], 'stat': {'season_id': 2086865, 'view': 3796707, 'danmaku': 18235, 'reply': 9546, 'fav': 139394, 'coin': 113355, 'share': 46788, 'now_rank': 0, 'his_rank': 0, 'like': 283187, 'vt': 0, 'vv': 0}, 'ep_count': 5, 'season_type': 1, 'is_pay_season': False, 'enable_vt': 0}, 'is_season_display': True, 'user_garb': {'url_image_ani_cut': ''}, 'honor_reply': {'honor': [{'aid': 1450404511, 'type': 4, 'desc': '热门', 'weekly_recommend_num': 0}]}, 'like_icon': '', 'need_jump_bv': False, 'disable_show_up_info': False, 'is_story_play': 1}}

#
# from functools import reduce
# from hashlib import md5
# import urllib.parse
# import time
# import requests
#
# mixinKeyEncTab = [
#     46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
#     33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
#     61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
#     36, 20, 34, 44, 52
# ]
#
#
# def getMixinKey(orig: str):
#     '对 imgKey 和 subKey 进行字符顺序打乱编码'
#     return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, '')[:32]
#
#
# def encWbi(params: dict, img_key: str, sub_key: str):
#     '为请求参数进行 wbi 签名'
#     mixin_key = getMixinKey(img_key + sub_key)
#     curr_time = round(time.time())
#     params['wts'] = curr_time  # 添加 wts 字段
#     params = dict(sorted(params.items()))  # 按照 key 重排参数
#     # 过滤 value 中的 "!'()*" 字符
#     params = {
#         k: ''.join(filter(lambda chr: chr not in "!'()*", str(v)))
#         for k, v
#         in params.items()
#     }
#     query = urllib.parse.urlencode(params)  # 序列化参数
#     wbi_sign = md5((query + mixin_key).encode()).hexdigest()  # 计算 w_rid
#     params['w_rid'] = wbi_sign
#     return params
#
#
# def getWbiKeys() -> tuple[str, str]:
#     '获取最新的 img_key 和 sub_key'
#     headers = {
#         'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
#         'Referer': 'https://www.bilibili.com/'
#     }
#     resp = requests.get('https://api.bilibili.com/x/web-interface/nav', headers=headers)
#     resp.raise_for_status()
#     json_content = resp.json()
#     img_url: str = json_content['data']['wbi_img']['img_url']
#     sub_url: str = json_content['data']['wbi_img']['sub_url']
#     img_key = img_url.rsplit('/', 1)[1].split('.')[0]
#     sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]
#     return img_key, sub_key
#
#
# img_key, sub_key = getWbiKeys()
#
# signed_params = encWbi(
#     params={
#         'foo': '114',
#         'bar': '514',
#         'baz': 1919810
#     },
#     img_key=img_key,
#     sub_key=sub_key
# )
# query = urllib.parse.urlencode(signed_params)
# print(signed_params)
# print(query)
#
# from src.utils import AuthUtil
#
# print(AuthUtil().get_Wbi())


# class Config:
#     LOGIN_COOKIE_PATH = "A.txt"
#
#
# # 情况 1：修改类属性
# Config.LOGIN_COOKIE_PATH = "B.txt"
# print(Config().LOGIN_COOKIE_PATH)  # 输出 "B.txt" (符合你的预期)
#
# # 情况 2：属性遮蔽 (Shadowing)
# c1 = Config()
# c1.LOGIN_COOKIE_PATH = "C.txt"  # 仅给 c1 这个实例创建了一个独立属性
#
# print(Config.LOGIN_COOKIE_PATH)  # 输出 "B.txt" (类属性没变)
# print(c1.LOGIN_COOKIE_PATH)  # 输出 "C.txt" (实例属性覆盖了类属性)
# print(Config().LOGIN_COOKIE_PATH)  # 输出 "B.txt" (新实例依然去类里找)


# biliV = BiliVideo("BV1ov42117yC")
# biliV.download_video_with_audio(save_video_path='output', save_audio_path='output', save_path='output')