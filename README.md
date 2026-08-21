# BiliTools

py 操控 bilibili 的小工具（后端 SDK）。提供统一的数据模型与业务服务，可被命令行、Web、GUI 等多种前端稳定调用。

## 快速上手

```python
from src.services import DressupService, EmoteService, GarbService, VideoService
from src.models import VideoQuality

# 1. 扫码登录（只需执行一次，cookie 保存到 assets/cookie/qr_login.txt）
from src.services import LoginService
LoginService().qr_login()

# 2. 获取视频信息（返回 VideoInfo 数据模型）
service = VideoService()
info = service.fetch_info("BV1ov42117yC")
print(info.title, info.owner.name, info.stat.num_dm)

# 3. 下载视频（默认最高清晰度 4K；文件名自动为 [标题](BV号).mp4）
result = service.download_video_with_audio("BV1ov42117yC")
print(result.path)

#    指定清晰度：精确匹配目标档位，该档不存在时回退到最高可用
result = service.download_video_with_audio("BV1ov42117yC", quality=VideoQuality.P1080)
#    P1080 在有 4K 的视频上会下 1080P（不会被拉到 4K）；无 1080P 档时回退到最高可用

# 4. 统一下载入口：只传 bvid，自动决定下载范围 + 最高清晰度 + 进度显示
#    - 属于合集 → 下载整个合集（含分P）
#    - 单视频 → 下载该视频（含分P）
service.download("BV1ov42117yC")     # 单视频
service.download("BV1Q43w6QETb")     # 属于合集 → 下载整个合集

# 5. 多P视频：指定分P下载 / 下载全部分P（文件名含 P 序号）
service.download_video_with_audio("BV1Q43w6QETb", page=2)          # 只下第2P
service.download_all_pages("BV1Q43w6QETb")                          # 下载全部分P

# 6. 合集下载：bvid 或 sid 任选其一
service.download_season("BV1Q43w6QETb")                  # 从合集内任意一个视频进入
service.download_season(season_id=8683221)                # 按 sid 直接下载（洛天依·纯蓝幻乐）
service.download_season(season_id=1717000, mid=506925078) # 下载他人合集（明日方舟）

# 7. 收藏夹下载：全部视频（有声音）或仅音频（缓存听歌），传 media_id
service.download_fav(3953119978)
service.download_fav(3953119978, mode="audio")            # 仅下载音频到 output/video/<收藏夹名>/

# 8. UP主空间下载：全部视频或仅音频，传 mid
service.download_up(249056021)
service.download_up(249056021, mode="audio")              # 仅下载音频到 output/video/<UP主昵称>/

# 9. 收藏表情包下载：支持单个或多个 package id；动态表情优先下载 GIF
EmoteService().download_packages("10239")
EmoteService().download_packages("10239,10238")             # 保存到 output/收藏集/<收藏集名>/<表情包类型>/
EmoteService().download_packages("10239", use_full_name=True)  # 文件名使用完整 text（默认使用 alias 简称）

# 10. 收藏集 / 装扮下载：按名称搜索，同名结果优先；资源统一保存到 output/收藏集/
GarbService().download_by_keyword("初音未来")
GarbService().download_by_keyword("初音未来", resource_types=["emoji_package", "space_bg"])

# 11. 装扮统一搜索：一次同时搜索表情包 / 收藏集 / 主题装扮，勾选后批量并发下载
items = DressupService().search("洛天依")
print([item.display_name for item in items])
DressupService().download_items([item.as_dict() for item in items], threads=2)
```

收藏夹视频列表获取：`FavService().get_fav_bv(media_id)`、`get_fav_info(media_id)`。
UP主视频列表获取：`service.list_up_videos(mid)`。
表情包详情获取：`EmoteService().get_packages("10239,10238")`。
收藏集/装扮可通过 `GarbService().search_items("关键词")` 搜索；收藏集下载封面、卡图和卡片视频，装扮按素材类别保存。
GUI 的「装扮」页签默认按关键词同时搜索三类内容，勾选结果后可批量下载，并支持并发线程与多账号分流。

> 注：视频、收藏夹、合集、UP 主、表情包后端接口接收规范 id（BV号 / media_id / mid / sid / package id）；
> 收藏集/装扮接口接收名称关键词。BV号、av号、完整链接、b23.tv 短链的解析统一由 GUI 前端完成（`frontend/pyside6/utils.py`）。

更多示例见 `examples/quick_start.py`，命令行入口见 `main.py`。

## 功能

| 模块 | 服务类 | 功能 |
|------|--------|------|
| 视频 | `VideoService` | 获取信息 / 下载视频 / 音频 / 封面 / 音视频合成（ffmpeg）/ **分P下载 / 合集下载 / 收藏夹下载 / UP主下载** |
| 登录 | `LoginService` | 扫码登录 / 登录状态查询 |
| 历史 | `HistoryService` | 历史记录分页 / 失效视频查找 / 导出 xlsx |
| 用户 | `UserService` / `ContractService` | 用户信息 / 老粉签约 |
| 评论 | `ReplyService` | 发表评论 |
| 私信 | `MessageService` | 发送私信 |
| 排行 | `RankService` | 综合热门 / 排行榜 |
| 收藏 | `FavService` | 收藏夹视频列表 / 收藏夹全部视频·音频下载 |
| 表情包 | `EmoteService` | 按一个或多个 package id 获取并下载全部表情（动态表情优先 GIF） |
| 收藏集/装扮 | `GarbService` | 按名称搜索并下载收藏集卡片或主题装扮素材（含表情包、空间海报等） |
| 装扮统一 | `DressupService` | 一次搜索表情包/收藏集/装扮，勾选后并发批量下载（可多账号分流） |
| 合集 | `ArchiveService` | 视频合集列表 |

## 项目结构

```
BiliTools/
├── main.py                # 命令行入口
├── examples/              # 使用示例
├── src/
│   ├── api/               # 统一请求层（BiliSession）、wbi签名、异常体系
│   ├── config/            # 路径锚点(path)、常量、Cookie
│   ├── models/            # 业务数据模型（dataclass）
│   ├── services/          # 业务服务（核心 API）
│   ├── urls/              # API URL 统一管理
│   └── util/              # BV/AV转换、文件名清洗、下载工具
├── assets/cookie/         # 扫码登录后的 cookie
├── output/                # 下载输出（video/ 视频，收藏集/ 表情包/装扮素材，history/ 表格）
└── tests/                 # 测试
```

## 依赖

- 运行时依赖见 `requirements.txt`：`requests, pandas, openpyxl, pillow, qrcode` 等。
- 音视频合成依赖系统安装 **ffmpeg** 并加入 PATH（通过 `subprocess` 调用，无法用 pip 安装）。参考安装视频 [BV1qw4m1d7hx](https://www.bilibili.com/video/BV1qw4m1d7hx/)。
- 开发测试依赖：`pytest`。

## 测试

```bash
pip install pytest
pytest tests/ -m "not network"    # 仅跑单元测试（不联网）
pytest tests/                     # 全部测试（含真实网络，需可访问 B 站）
```

## 迁移说明

本项目已从「示例脚本集合」重构为「分层 SDK」。旧模块（`src/video.py` 等）已删除，
新代码统一使用 `src/services/` 下的服务类，数据通过 `src/models/` 的 dataclass 传递，
路径由 `src/config/path.py` 统一管理，失败通过 `src/api/errors.py` 的异常体系表达。
