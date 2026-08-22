# BiliTools

BiliTools 是一个用 Python 操控 bilibili 的工具集，提供 **后端 SDK、命令行入口和 PySide6 桌面 GUI**。项目把「输入解析、API 请求、数据模型、下载与进度显示」拆成独立层，便于继续接入 Web 或其他前端。

> 完整的后端 API、数据流、GUI 操作和参数说明见 [`docs/功能介绍.md`](docs/功能介绍.md)。本 README 只保留quick start。

## 1. 安装与运行

```bash
# 建议在项目根目录创建并激活虚拟环境
pip install -r requirements.txt

# 启动桌面 GUI
python -m frontend.pyside6

# 或使用命令行
python main.py --help
```

下载视频并合成音频需要 ffmpeg。可以安装系统 ffmpeg 并加入 PATH，也可以安装项目支持的内置后端：

```bash
pip install imageio-ffmpeg
```

GUI 首次启动会在后台检查登录状态。点击「登录」页的「登录新账号」，使用哔哩哔哩 App 扫码即可；账号 cookie 默认保存在 `%APPDATA%/xiaoman/BiliTools/cookie/`（Windows），多账号映射保存在同目录的 `accounts.json`。

## 2. 最快下载一个视频

### 桌面 GUI

1. 启动 `python -m frontend.pyside6`。
2. 在「登录」页扫码登录。
3. 回到「下载」页，在「视频 BV」页签粘贴 BV 号、av 号或视频链接（支持短链b23.tv）。
4. 选择保存目录、清晰度和分P（可以只使用默认值而不调整），点击「开始下载」。
5. 进度、ffmpeg 合成阶段和错误信息会显示在任务区/日志区。

### Python SDK

```python
from src.models import VideoQuality
from src.services import LoginService, VideoService

# 只需首次执行，cookie 会被保存并供后续 BiliSession 自动使用
LoginService().qr_login()

service = VideoService()

# 获取信息：返回 VideoInfo，而不是未约定结构的字典
info = service.fetch_info("BV1ov42117yC")
print(info.title, info.owner.name, info.stat.num_view)

# 下载视频 + 音频合成；默认目标为 4K，实际没有该档位时回退到最高可用档
result = service.download_video_with_audio("BV1ov42117yC")
print(result.path, result.cached)

# 指定清晰度时精确匹配；没有 1080P 时才回退到最高可用档
result = service.download_video_with_audio("BV1ov42117yC", quality=VideoQuality.P1080)
```

统一下载入口会自动判断范围：属于合集时下载整个合集；普通视频时下载全部分P。

```python
service.download("BV1ov42117yC")
```

## 3. 主要功能

| 模块 | 入口 | 说明 |
|---|---|---|
| 视频 | `VideoService` | 信息、标签、视频流、音频、封面、音视频合成、分P、合集、收藏夹、UP主投稿下载 |
| 登录/账号 | `LoginService` / `AccountManager` | 扫码登录、登录状态、多账号切换、cookie 管理 |
| 历史 | `HistoryService` | 游标分页、失效视频查找、导出 xlsx |
| 收藏/合集 | `FavService` / `ArchiveService` | 获取收藏夹信息、BV 列表和合集结构 |
| 表情/装扮 | `EmoteService` / `GarbService` / `DressupService` | 表情包、收藏集、主题装扮搜索与批量下载 |
| 用户/互动 | `UserService`、`ReplyService`、`MessageService`、`ContractService` | 用户信息、评论、私信、老粉签约 |
| 榜单 | `RankService` | 综合热门、排行榜、新视频 |

其他常用示例：

```python
from src.services import EmoteService, GarbService, VideoService

# 多P、合集、收藏夹、UP主
service = VideoService()
service.download_video_with_audio("BV1Q43w6QETb", page=2)
service.download_all_pages("BV1Q43w6QETb")
service.download_season(season_id=8683221)
service.download_fav(3953119978, mode="audio")
service.download_up(249056021)

# 表情包、收藏集和装扮
EmoteService().download_packages("10239,10238")
GarbService().download_by_keyword("初音未来")
```

完整参数、接口返回值、后端调用链和 GUI 的每个来源页签见 [`docs/功能介绍.md`](docs/功能介绍.md)。示例已按功能拆分到 [`examples/`](examples/)（索引见 [`examples/README.md`](examples/README.md)）；最简单的扫码登录+视频下载示例是 [`examples/quick_start.py`](examples/quick_start.py)。

## 4. 命令行快速入口

```bash
python main.py info BV1ov42117yC   # 标题、UP主、播放/弹幕/评论、标签
python main.py video BV1ov42117yC  # 下载视频并合成音频
python main.py cover BV1ov42117yC  # 下载封面
python main.py rank                # 获取热门视频 BV 号
```

## 5. 数据流概览

```text
GUI / CLI / examples
        │ 规范化输入：BV、fid、sid、mid、package id
        ▼
src/services/                 面向场景的业务流程
        │ 调用统一 URL + BiliSession
        ▼
src/api/session.py            Cookie、User-Agent、Referer、重试、code 检查
src/api/auth.py               wbi 签名（需要时）
        │ 返回 API data
        ▼
src/models/                   dataclass：VideoInfo、DashStreams、HistoryPage…
        │
        ├─ 下载工具：断点续传、ffmpeg、文件名、进度
        └─ GUI 信号：进度/阶段/完成/错误
```

以视频下载为例：`bvid → VIEW 获取 VideoInfo → 解析 pages 得 cid → PLAY 获取 DASH 视频/音频 URL → 下载到临时文件 → ffmpeg 合成 → DownloadResult`。已有文件会先命中缓存，避免重复请求。

## 6. 测试与打包

```bash
pytest tests/ -m "not network"  # 单元测试，不联网
pytest tests/                   # 包含真实网络测试
pyinstaller bilitools.spec --noconfirm
```

写操作（评论、私信、老粉签约）需要有效登录和 `bili_jct`；4K/HDR/杜比等档位还取决于账号权限。
请遵守 bilibili 用户协议及相关法律法规，仅将本项目用于个人学习和合规用途。