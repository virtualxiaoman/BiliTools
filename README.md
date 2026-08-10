# BiliTools

py 操控 bilibili 的小工具（后端 SDK）。提供统一的数据模型与业务服务，可被命令行、Web、GUI 等多种前端稳定调用。

## 快速上手

```python
from src.services import VideoService
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
```

更多示例见 `examples/quick_start.py`，命令行入口见 `main.py`。

## 功能

| 模块 | 服务类 | 功能 |
|------|--------|------|
| 视频 | `VideoService` | 获取信息 / 下载视频 / 音频 / 封面 / 音视频合成（ffmpeg）/ **分P下载 / 合集下载** |
| 登录 | `LoginService` | 扫码登录 / 登录状态查询 |
| 历史 | `HistoryService` | 历史记录分页 / 失效视频查找 / 导出 xlsx |
| 用户 | `UserService` / `ContractService` | 用户信息 / 老粉签约 |
| 评论 | `ReplyService` | 发表评论 |
| 私信 | `MessageService` | 发送私信 |
| 排行 | `RankService` | 综合热门 / 排行榜 |
| 收藏 | `FavService` | 收藏夹视频列表 |
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
├── output/                # 下载输出（video/ 视频，history/ 表格）
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
