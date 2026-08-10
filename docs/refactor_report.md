# BiliTools 后端重构分析与设计报告

> 日期：2026-08-10
> 范围：后端 `src/` 全量重写、仓库结构与路径管理、前后端解耦（前端 UI 另立项目，不在本报告范围内）
> 目标：将「demo 风格的示例脚本集合」重构成「语义清晰、可维护、可被 UI 稳定调用的后端 SDK」

---

## 一、现状总览

### 1.1 项目结构（实际）

```
BiliTools/
├── main.py                    # 快速上手示例（真正的入口散落在 __main__ 注释里）
├── test.py / src/test_code.py # 临时测试脚本
├── src/
│   ├── config.py              # Config(路径/重试参数) + BiliCookies(cookie 解析) + UserAgent
│   ├── utils.py               # BV2AV + AuthUtil(wbi) + BiliVideoUtil(下载/保存/路径) + hmac_sha256
│   ├── video.py               # VideoUrls + BiliVideo（核心类）
│   ├── history.py             # BiliHistory（历史记录）
│   ├── login.py               # LoginUrls + BiliLogin（扫码登录）
│   ├── up.py                  # BiliUserInfo + BiliContract（老粉/签约）
│   ├── archive.py             # BiliFav(收藏夹) + BiliArchive(合集)
│   ├── rank.py / reply.py / message.py
│   ├── util/Colorful_Console.py
│   ├── cookie/                # cookie_大号.txt 等（与 assets/cookie/ 重复）
│   └── output/                # 历史记录 xlsx/json/txt（已 gitignore）
├── assets/cookie/             # Config.COOKIE_PATH 指向这里
├── frontend/                  # PyQt UI（将全部重写）
├── build/ dist/ venv/         # 打包产物与虚拟环境（build/dist 已 gitignore）
└── output/                    # 下载视频（已 gitignore）
```

### 1.2 一句话结论

代码不是「混乱」，而是「**没有分层**」：API URL、请求构造、响应解析、数据模型、文件保存、错误处理、日志全部揉在一起，且大量功能点互相复制。重写的核心是把「抓取」与「数据」分开，把「下载」从「数据对象」里剥离，并统一路径/URL/错误/日志四套基建。

---

## 二、需求分析（按你的要求逐条展开）

| # | 需求 | 含义 |
|---|------|------|
| 1 | `BiliVideo` 用 dataclass 重写 | 把一堆手写 `self.xxx = None` 的属性集收敛为类型化的数据类，从 API 响应构造；抓取方法不再把数据挂在实例上 |
| 2 | 语义化命名（`dm` → `num_dm`） | 所有缩写改成可读名称：`dm→num_dm`、`view→num_view`、`reply→num_reply`(使用num开头方便管理全部的数据信息)、`up→up_name`、`time→pub_time` 等 |
| 3 | 下载 API 语义正确 | 只传「保存目录」，文件名自动生成 `[标题](BV号).mp4`；扩展名由实际流格式决定，不写死 |
| 4 | URL 统一管理 | 按业务域用 dataclass 分组维护（视频/用户/登录/历史/评论/私信/排行/收藏…），消灭字符串散落 |
| 5 | 路径统一管理 | 新建 `src/config/path.py`，`PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent` 作为一切路径锚点，消除相对路径对 cwd 的依赖 |

---

## 三、具体问题清单（按模块）

### 3.1 仓库与工程层面

1. **路径锚点缺失，依赖 cwd**。`Config.COOKIE_PATH = "./assets/cookie/qr_login.txt"`（`src/config.py:5`）、下载目录 `"output"`（`frontend/download_ui.py:47`）、临时文件 `"output/temp_last_cursor.txt"`（`src/history.py:125`）等全部是相对路径。从不同目录启动程序，读写位置完全不同。
2. **cookie 目录两处并存**。`src/config.py` 指向 `assets/cookie/`，但 `src/cookie/` 下也放着 `cookie_大号.txt`；`src/login.py` 的默认参数 `"./assets/cookie/qr_login.txt"`（`login.py:168`）。应统一到一处，由 `path.py` 派生。统一保存在assets/cookie/qr_login.txt（默认）下，也支持指定路径（当前cookie使用什么路径也全局管理，避免每个类都要传入cookie文件的参数）。前端界面也默认保存在这里，除非传入参数否则不要保存在前端的文件夹下。
3. **输出目录两处并存**。根目录 `output/` 与 `src/output/` 都有产物；`.gitignore` 同时 ignore 了 `/output/` 和 `/src/output/`。应统一为 `OUTPUT_DIR`。例如视频下载到output/video下，历史信息下载到output/history下。
4. **`requirements.txt` 是 UTF-16 编码**（Windows 老工具生成），在 Linux/CI 下 `pip install -r` 可能解析失败；且未声明 `ffmpeg`（README 明确说音视频合成需要它）。应重写为 UTF-8 并补齐说明。
5. **垃圾文件未治理**：`src/temp.json`（45KB）、`src/test_code.py`、`test.py`、`src/output/temp_*.xlsx` 混在源码里；`.gitignore` 未覆盖 `.idea/`、`__pycache__/`、`venv/`、`build/`、`dist/`。
6. **README 的项目结构图与实际不符**（README 里写的 `src/bili_tools.py`、`bili_util.py` 不存在；UI 目录实际叫 `frontend`）。
7. **前后端强耦合**：`frontend/download_ui.py:12-16` 直接 `from src.video import BiliVideo`，UI 线程里 `new BiliVideo()` 就会发起 2~3 个 HTTP 请求（见 3.2 第 2 条），且 UI 里自己实现了文件名清洗/拼装（`frontend/download_ui.py:65-89`）。这些逻辑必须下沉到后端，UI 只调新 API。

### 3.2 `BiliVideo` / `BiliVideoUtil`（`src/video.py`、`src/utils.py`）

1. **手写属性初始化堆积**（`video.py:99-127`）：`title/pic/desc/stat/view/dm/reply/time/like/coin/fav/share/tag/tid/tname/up/up_mid/up_follow/up_followers/user_like/user_coin/user_fav` 等 20+ 个属性先全部置 `None`，再在 `get_content()` 里逐个赋值。正是你指出的「可以用 dataclass」的点。
2. **构造即请求（构造器副作用）**：`BiliVideoUtil.__init__` 里就同步请求两次——检查 `accessible`（`utils.py:323-339`）+ 获取 `cid`（`utils.py:341-354`）；`BiliVideo.__init__` 再调 `AuthUtil().get_wbi()`（`video.py:71`）又请求一次 `nav`。UI 线程一次 `new BiliVideo` 至少 3 个网络请求。**数据获取应显式调用，不隐含在构造里**。
3. **下载参数语义混乱**（`video.py:199-200`）：
   - `save_video_path` + `save_video_name` + `save_video_add_desc` + `full_path` 四者互相覆盖（`full_path` 一指定其余全失效，`_get_path` 里判断），调用方很难说清「到底存哪、叫什么」。
   - `save_video_add_desc="视频(无音频)"` 这种默认值把「描述」和「文件名」耦合——文件名长这样：`BV号视频(无音频).mp4`。
   - `qn` 参数传入后被写死为 120（`video.py:219`），`fnval` 写死 4048，参数实际上不可用。
   - 请求前有一堆调试残留 `print(params)`（`video.py:227-229`）。
4. **`dm` 等无语义命名**（`video.py:104,158`），并传导到 `to_csv()` 的列名（`video.py:442-450`）和 `history.py` 的 DataFrame 列（`history.py:176-188`）。README 第 64 行的字段表也是这些名字，需同步。
5. **文件名清洗逻辑在前端**：`frontend/download_ui.py:78-79` 用正则去掉标题里非法字符和空白——这属于下载 API 的本职，应下沉后端统一实现（你要求的 `[标题](BV号).mp4` 格式）。
6. **四个几乎重复的保存函数**：`_save_mp4/_save_mp3/_save_pic` + `_get_path`（`utils.py:220-285`），逻辑完全相同、仅后缀和默认 desc 不同；`check_path` 同时支持 str/list/None 三种入参（`utils.py:201-218`），可收敛成一个 `_save_content(path, content)` 或直接由 `Path.mkdir(parents=True, exist_ok=True)` 替代。
7. **`merge_video_audio` 用 `os.system` 拼 ffmpeg**（`utils.py:194-199`）：依赖 shell、同步阻塞、返回 `-1` 表示失败，且调用方不检查返回值（`video.py:307`）。
8. **错误处理用 `return False / None / -1 / 114514 / print("再见ヾ")` 混合**（`video.py:144,174,180,331-332`；`utils.py:196`；`history.py:92-96,320`；`reply.py:51`）。没有异常体系，UI 无法判断失败原因。
9. **`to_csv` 语义错误**：`get_content()` 未调用时属性全为 `None`，导出的是空列；列名 `dm` 需改 `num_dm`。
10. **重复初始化（冗余网络请求）**：`BiliVideo` 每次实例化都重新拉 `cid`、重新算 wbi，前端 `get_name()` 里为拿个标题就 `new BiliVideo + get_content`（`frontend/download_ui.py:75-76`），大量浪费。

### 3.3 URL 管理

1. **已有雏形但没被使用**：`VideoUrls`（`video.py:13-21`）定义了几个 URL，但 `BiliVideo` 又手写了一遍 `self.url_play/url_stat/url_stat_detail/url_tag/url_up/videoshot_url`（`video.py:80-85`），两处不一致（`url_up` 用的是 `/x/web-interface/card`，与 `VideoUrls.VIEW` 来自不同接口）。
2. **URL 字符串散落全库**，且域名 `https://www.bilibili.com`、`https://api.bilibili.com` 重复出现：
   - `src/utils.py:329,343`（view / pagelist）
   - `src/history.py:23`（history/cursor）
   - `src/login.py:11-14`（已有 `LoginUrls`）
   - `src/up.py:20-21`（space/acc/info）
   - `src/rank.py:16-18`、`src/archive.py:18,50`、`src/reply.py:39`、`src/message.py:18`
   - referer 各写各的：`video.py:91`、`utils.py:318`、`history.py:22`、`archive.py:32,38`、`up.py:35` 等。
3. **你的方案**：按业务域建 dataclass 组——`VideoUrls`、`UserUrls`、`LoginUrls`、`HistoryUrls`、`RankUrls`、`CommentUrls`、`MessageUrls`、`FavUrls` 等，全部只接受参数方法生成完整 URL；基础域名常量放 `src/config/constants.py`。

### 3.4 路径管理（`src/config/path.py` 新模块）

按你的要求，新增：

```python
# src/config/path.py
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # BiliTools/
ASSETS_DIR   = PROJECT_ROOT / "assets"
COOKIE_DIR   = ASSETS_DIR / "cookie"
OUTPUT_DIR   = PROJECT_ROOT / "output"
DEFAULT_COOKIE_PATH = COOKIE_DIR / "qr_login.txt"
QR_IMAGE_PATH = COOKIE_DIR / "qr_login.png"

def ensure_dirs() -> None:
    for d in (ASSETS_DIR, COOKIE_DIR, OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
```

- 此后全库不得再出现裸相对路径，一律 `from src.config.path import OUTPUT_DIR`。
- `Config` 里的 `COOKIE_PATH`、前端 `ui_config.json` 里的 `cookie_path/qr_path/video_path` 等全部改为引用这些常量（或由后端直接提供，UI 不再存路径配置）。

### 3.5 `src/config.py` 问题

1. **职责混杂**：`Config`（静态参数）、`BiliCookies`（读文件 + 解析 cookie）、`UserAgent`（UA 字符串）挤在一个文件。建议拆为 `constants.py`（UA、重试参数、基础域名）+ `cookie.py`（Cookie 模型：读取、解析 SESSDATA/bili_jct、保存）。
2. **`BiliCookies` 每次实例化都重读文件**（`config.py:12-21`），且 `reply.py:45`、`up.py:34,112,115` 等在每次请求时才 `cookies()` —— 应改为**进程内一次读取 + 缓存**（带校验），需要重新登录时才刷新。
3. **解析失败直接 `exit(1)` 杀进程**（`config.py:39-40,53-54`）：库代码里绝不能 `exit()`，应抛异常由上层决定（UI 弹窗、CLI 报错）。
4. **cookie 解析逻辑重复两套**：`config.py:27-55` 用 `split(";")` 解析，`login.py:203-214` 用正则再解析一遍。应统一为一个 `Cookie.parse(raw)`。

### 3.6 其余模块

- **`history.py`**：
  - 分页游标逻辑在 `get_history` / `get_history_all` / `get_invalid_video` 里复制了三份（`history.py:59-96,99-127,286-330`），应抽一个公共分页器。
  - `save_video_history_df` 里同步串行 `new BiliVideo` 拉取每个视频详情（`history.py:191-216`），无重试、无并发、每 25 个做一次 checkpoint，性能与稳定性都差；且 `get_user_action` 内部又是 3 个请求。
  - 写 `output/temp_last_cursor.txt` 用硬编码路径（`history.py:125`）。
- **`login.py`**：`qr_login` 在 `while True` 里轮询阻塞 60 秒（`login.py:145-166`），UI 必须开线程；`img.show()` 依赖本机图片查看器。若 UI 重写，建议后端只提供「生成二维码 + 一次 poll」的无状态接口，轮询交给 UI。
- **`up.py`**：`BiliUserInfo` 硬编码了 `w_webid` JWT（`up.py:96`），极易过期失效，且注释里已标注参数失效（`up.py:28-30`）——这类风控参数需要预留可配置注入点，不能写死。`BiliContract`（老粉签约）与用户信息是两个业务，应拆文件。
- **`archive.py`**：文件名与内容不符——`archive.py` 里同时有 `BiliFav`（收藏夹）和 `BiliArchive`（合集）；且 `__init__` 里调 `BiliLogin(headers).get_login_state()` 请求登录态（`archive.py:33,53`），构造即请求问题同样存在。
- **`rank.py` / `reply.py` / `message.py`**：基本是「一个方法一个类」，直接函数化或统一为薄 service。
- **`utils.py`**：`BV2AV` 方法全部无状态却用实例方法（每次 `BV2AV().bv2av()`），建议静态方法/单例；文件中部 `import hmac/hashlib` 和尾部 `__main__` 里的 `hmac_sha256` 示例代码应移除。
- **日志**：全库 `print` + 手写 `[BiliLogin-xxx]` 前缀（`login.py:46,60,76,142` 等），格式不统一、无级别、无法关闭。统一 `logging`，请求错误与业务提示分离。

---

## 四、重写设计方案

### 4.1 目标目录结构

```
BiliTools/
├── main.py                        # 仅保留 CLI 入口（demo 代码移入 examples/）
├── examples/                      # 原 main.py 与各 __main__ 示例迁移至此
├── src/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── session.py             # requests.Session 工厂（headers/cookie/重试/超时）
│   │   ├── errors.py              # BiliAPIError 体系
│   │   └── auth.py                # wbi 签名、buvid、ticket（原 AuthUtil + hmac_sha256）
│   ├── constants.py               # 基础域名、UA、重试参数（原 Config 静态部分）
│   ├── cookie.py                  # Cookie 模型：读取/解析/缓存/保存（原 BiliCookies）
│   ├── config/
│   │   └── path.py                # PROJECT_ROOT 与全部路径常量（你指定的方案）
│   ├── models/
│   │   ├── __init__.py
│   │   ├── video.py               # VideoStat/VideoInfo/VideoOwner 等 dataclass + from_dict
│   │   ├── user.py                # UserInfo dataclass
│   │   ├── history.py             # HistoryItem dataclass
│   │   └── ...                    # rank/reply/message 各自的数据类
│   ├── urls/
│   │   ├── __init__.py
│   │   ├── video.py               # class VideoUrls（dataclass/类常量 + 参数方法）
│   │   ├── user.py / login.py / history.py / rank.py / comment.py / message.py / fav.py
│   ├── services/
│   │   ├── video.py               # VideoService：fetch_info / download（解耦自数据模型）
│   │   ├── login.py               # LoginService：qr 生成/一次 poll（无阻塞轮询）
│   │   ├── history.py             # HistoryService：分页游标复用
│   │   ├── up.py / rank.py / reply.py / message.py / archive.py
│   └── util/
│       ├── filename.py            # sanitize_filename() + 统一命名规则 [标题](BV).ext
│       ├── downloader.py          # 下载流 + ffmpeg 合并（subprocess 列表参数，返回码检查）
│       └── bvid.py                # BV2AV（静态方法）
├── assets/cookie/                 # 唯一 cookie 目录
├── output/                        # 唯一输出目录
└── tests/
```

> 依赖方向：`services → {api, models, urls, config, util}`；`models/urls/api` 互相不依赖；`src/` 不依赖 `frontend/`。UI 通过 `services` 层取数据、拿 dataclass 渲染。

### 4.2 数据模型（dataclass 重写 `BiliVideo`）

用类型化 dataclass 替代 20+ 个手写属性，并配套 `from_dict` 从 API 响应构造：

```python
# src/models/video.py
from dataclasses import dataclass, field

@dataclass
class VideoOwner:
    mid: int
    name: str
    face: str | None = None
    is_followed: bool | None = None      # 原 up_follow(0/1)
    num_follower: int | None = None    # 原 up_followers

@dataclass
class VideoStat:
    num_view: int = 0          # 原 view
    num_dm: int = 0              # 原 dm
    num_reply: int = 0         # 原 reply
    num_like: int = 0          # 原 like
    num_coin: int = 0          # 原 coin
    num_fav: int = 0           # 原 fav
    num_share: int = 0         # 原 share

@dataclass
class VideoInfo:
    bvid: str
    aid: int
    cid: int | None = None
    title: str = ""
    pic: str = ""                          # 封面 URL
    desc: str = ""
    pub_time: int = 0                      # 原 time (pubdate)
    tid: int = 0
    tname: str = ""
    tags: list[str] = field(default_factory=list)
    stat: VideoStat = field(default_factory=VideoStat)
    owner: VideoOwner | None = None
    user_action: UserAction | None = None  # 原 user_like/user_coin/user_fav

    @classmethod
    def from_view_json(cls, bvid: str, data: dict) -> "VideoInfo": ...
    @classmethod
    def from_detail_json(cls, bvid: str, data: dict) -> "VideoInfo": ...
```

要点：

- **`VideoService.fetch_info(bvid)` 返回 `VideoInfo`**，而不是把数据塞进 `self`。要重新拉取就再调一次方法拿新对象，天然规避「构造即请求 + 数据可变」的问题。
- 命名语义化贯穿到底：`dm→num_dm`、`time→pub_time`、`up→owner.name`、`up_follow→is_followed`。
- 布尔字段直接用 `bool`，不再用 0/1 魔法数。
- `to_csv`/DataFrame 导出改为「从一个 `VideoInfo` 列表构建」，列名同步改为 `num_dm/pub_time/...`，README 字段表一并更新。

### 4.3 URL 统一管理

按业务域分组，基础域名收敛到 `src/constants.py`：

```python
# src/constants.py
API_BASE   = "https://api.bilibili.com"
API_PASS   = "https://passport.bilibili.com"
API_VC     = "https://api.vc.bilibili.com"
WEB_BASE   = "https://www.bilibili.com"

# src/urls/video.py
class VideoUrls:
    # 类常量：无参数的固定端点
    VIEW      = f"{API_BASE}/x/web-interface/view"
    PLAY      = f"{API_BASE}/x/player/wbi/playurl"
    PAGELIST  = f"{API_BASE}/x/player/pagelist"
    TAGS      = f"{API_BASE}/x/tag/archive/tags"
    VIDEO_SHOT= f"{API_BASE}/x/player/videoshot"
    CARD      = f"{API_BASE}/x/web-interface/card"

    # 参数方法：需要拼接参数/路径的端点
    @staticmethod
    def video_page(bvid: str) -> str:
        return f"{WEB_BASE}/video/{bvid}"

    @staticmethod
    def view_detail(bvid: str) -> str: ...
    @staticmethod
    def user_action_like(aid: int) -> str: ...
```

- 规则：**固定端点为类常量，需要路径参数的为静态方法**；每个业务域一个模块，`src/urls/__init__.py` 统一导出。
- 全局搜索消灭所有裸 URL 字符串与裸 referer，referer 由 `session.py` 按接口域自动填默认值。

### 4.4 下载 API 语义重构

**原则：只告诉它「存到哪个目录」，文件名与扩展名由后端根据内容决定。**

```python
# src/services/video.py
class VideoService:
    def __init__(self, cookie: Cookie, session: requests.Session = ...): ...

    def download_video(self, bvid: str, dir: Path = OUTPUT_DIR,
                       *, quality: Quality = Quality.P1080) -> DownloadResult:
        """
        下载视频流（无音频）到 dir，文件名自动为 {sanitize(title)}({bvid}).{ext}。
        ext 由实际 DASH 流格式决定（mp4/flv），不写死。
        """
        info = self.fetch_info(bvid)
        streams = self._playurl(bvid, info.cid, quality=quality)   # dash 流解析
        ext = Path(streams.video[0].url).suffix or ".mp4"
        filename = f"{sanitize_filename(info.title)}({info.bvid}){ext}"
        self._download(streams.video[0], dir / filename, progress_cb=...)
        return DownloadResult(path=dir / filename, media_type="video")

    def download_audio(self, bvid: str, dir: Path = OUTPUT_DIR, ...) -> DownloadResult: ...
    def download_video_with_audio(self, bvid: str, dir: Path = OUTPUT_DIR,
                                  *, merge: bool = True, progress_cb=...) -> DownloadResult: ...
    def download_cover(self, bvid: str, dir: Path = OUTPUT_DIR) -> DownloadResult: ...
```

要点：

- **参数从 4 个互相覆盖的字符串收敛为 1 个 `dir`**；`full_path`、`add_desc` 等全部删除。
- **`[标题](BV号).mp4` 命名内置**（你要求的格式），由 `util/filename.py` 统一实现：`sanitize_filename()`（去除 `\ / : * ? " < > |`、控制字符、Windows 保留名、超长截断）+ 拼 `({bvid})` + 真实扩展名。UI 不再自己拼文件名（删掉 `frontend/download_ui.py:65-89`）。
- **音视频合并**：`downloader.py` 用 `subprocess.run(["ffmpeg","-i",video,"-i",audio,"-c","copy","out"], check=True)` 列表参数，避免 shell 注入与引号问题；检查返回码，合并前保证两个中间文件都成功下载；临时文件放 `dir/.tmp/` 或系统临时目录，失败时清理。
- **返回 `DownloadResult`**（dataclass：`path/type/size`），失败抛 `DownloadError`，不再 `return False`。
- **`quality` 用枚举**（`VideoQuality`：P360/P480/P720/P720_60/P1080/P1080_PLUS/P1080_60/HD4K/HDR/DOLBY/HD8K，qn 值对齐 BAC 文档），`fnval` 统一常量，不再暴露易错魔法数。
- 预留 `progress_cb`（bytes_done, total）回调，方便 UI 展示进度，后端保持无 UI 依赖。

### 4.5 统一错误处理与日志

```python
# src/api/errors.py
class BiliError(Exception): ...
class BiliAuthError(BiliError): ...          # code=-101 未登录 等
class VideoNotFoundError(BiliError): ...     # 视频不存在/失效
class BiliAPIRetryableError(BiliError): ...  # 可重试（-412 风控等）
class DownloadError(BiliError): ...

# src/api/session.py
def check_code(r: requests.Response) -> dict:
    """所有 API 响应统一过这一关：code!=0 抛对应异常，正常返回 data dict。"""
```

- 统一 `check_code` 替代全库 `if r_json["code"] != 0: print(...); return False`。
- 所有模块 `import logging; logger = logging.getLogger(__name__)`，移除手写前缀 print；重试（`Config.MAX_RETRY/RETRY_DELAY`）封装进 `session.py` 的请求函数。

### 4.6 各 service 重写要点

- **login**：提供 `generate_qr() -> (qrcode_url, qrcode_key)` 与 `poll(qrcode_key) -> LoginResult` 两个无状态方法，**不再内部 while 阻塞**；cookie 解析/保存统一到 `src/cookie.py`。
- **history**：抽 `cursor_page()` 公共分页方法；`HistoryService` 返回 `HistoryItem` dataclass 列表；`save_video_history_df` 改为「输入 `VideoInfo` 列表 → 导出」，详情拉取支持重试与并发，去掉 25 个 checkpoint 的魔法行为（改为失败重试 + 最终一次写入）。
- **up**：`BiliUserInfo` 的 wbi 风控参数改造为可注入配置（不硬编码 `w_webid`）；`BiliContract` 拆出。
- **archive**：拆成 `FavService`（收藏夹）与 `ArchiveService`（合集），去掉构造时登录请求。
- **rank/reply/message**：函数化薄封装，URL 移入 `src/urls/`。

---

## 五、重构里程碑（建议落地顺序）

| 阶段 | 内容 | 产出 |
|------|------|------|
| **M0 基建** | 建 `src/config/path.py`、目录重组、`.gitignore` 补全、`requirements.txt` 重写为 UTF-8、删除垃圾文件（`src/temp.json`、`test_code.py`、`src/output/*`） | 干净的仓库 + 路径锚点 |
| **M1 底层** | `constants.py`、`cookie.py`（缓存 + 异常化）、`api/{session,errors,auth}.py`、`urls/*`、`util/{bvid,filename}` | 基建四件套（URL/路径/错误/日志）+ Cookie 单例 |
| **M2 视频** | `models/video.py`、`services/video.py`（fetch_info + 下载 + 合并 + 封面）、命名规则、`DownloadResult` | 核心 API 定型，`BiliVideo` 被替换 |
| **M3 其他 service** | login/history/up/rank/reply/message/archive 逐个重写，统一 `check_code` | 全功能后端 |
| **M4 前端对接** | 前端重写时只依赖 `services` 层返回的 dataclass；约定 `progress_cb` 与异常类型作为 UI 协议 | 前后端解耦 |
| **M5 清理** | 删除旧 `video.py/utils.py` 等、迁移示例到 `examples/`、更新 README | 收尾 |

**M2 是重头**：`BiliVideo` 的重写（dataclass + 下载语义）决定整个 SDK 的 API 形状，建议 UI 重写前先定稿 M2，用 `main.py` 或 `examples/` 跑通「`fetch_info` → `download_video_with_audio` → 得到 `[标题](BV号).mp4`」。

---

## 六、风险与注意事项

1. **向后兼容**：原 API（`BiliVideo`、`download_video(save_video_path=...)` 等）在旧 `frontend/` 与用户脚本中使用。M0~M2 期间建议保留旧模块并标注 deprecated，前端重写完成后再删除；或直接一次性替换并同步改 `main.py`。
2. **cookie 权限**：迁移 cookie 目录时，`assets/cookie/` 下的真实登录 cookie 不能丢失；确认 `src/cookie/` 与 `assets/cookie/` 哪份是最新，统一后删另一份（**删除前先人工确认**）。
3. **风控参数**（`up.py` 的 `w_webid`、`dm_img_*` 指纹）容易过期，重写时抽象成可配置项并记录获取方式，避免再次硬编码死值。
4. **ffmpeg**：合并依赖系统 ffmpeg，README 已声明；`downloader.py` 需在缺 ffmpeg 时给出明确异常（`ffmpeg -version` 探测一次并缓存结果）。
5. **命名与 UI 约定**：`[标题](BV号).mp4` 是 UI 默认行为，但应允许调用方通过 `filename` 覆盖参数自定义；清洗规则（`\ / : * ? " < > |`、全角字符、长度上限）集中一处，前端不要再实现第二份。

---

## 七、重构进度

### M0 已完成（2026-08-10）

- 新建 `src/config/path.py`：`PROJECT_ROOT` 锚点 + 全部路径常量（`ASSETS_DIR/COOKIE_DIR/OUTPUT_DIR/VIDEO_OUTPUT_DIR/HISTORY_OUTPUT_DIR/DEFAULT_COOKIE_PATH/QR_IMAGE_PATH/ensure_dirs`）。
- 新建 `src/config/constants.py`：基础域名、`UserAgent`、重试参数、`DASH_FNVAL`、超时。
- 新建 `src/config/cookie.py`：`BiliCookies` dataclass——统一解析（SESSDATA/bili_jct）、进程内缓存（`from_file`/`refresh`）、异常化（不再 `exit(1)`）、`to_headers()` 生成请求头。
- 删除旧 `src/config.py`，替换为 `src/config/` 包；`legacy_shim.py` 提供 `Config/BiliCookies/UserAgent` 兼容导入，**旧模块全部可继续 import**。
- 重写 `requirements.txt` 为 UTF-8；更新 `.gitignore`（补 `/.idea/`、`/venv/`、`__pycache__/`、cookie 敏感文件排除，保留 `/其他信息/` 等）；删除垃圾文件 `src/temp.json`、`src/test_code.py`、`test.py`、`src/output/`。

### M1 已完成（2026-08-10）

- `src/api/errors.py`：统一异常体系（`BiliError` + `BiliAuthError/-101`、`BiliForbiddenError/-403`、`BiliRiskError/-412`、`BiliAPIError`、`VideoNotFoundError/-404`、`DownloadError`、`FFmpegNotFoundError`），`raise_for_code()` 集中错误映射。
- `src/api/auth.py`：`get_wbi()`（带 img/sub_key 缓存）、`get_dev_id()`、`get_timestamp()`、`hmac_sha256()`。
- `src/api/session.py`：`BiliSession`——统一 UA/Referer/Cookie 注入、自动 `raise_for_code`、失败重试；`get/post` 返回业务 `data`。
- `src/urls/*`：按业务域分组（`video/user/login/history/rank/comment/message/fav/archive/contract`），基础域名收敛到 `constants.py`。
- `src/util/bvid.py`：`av2bv/bv2av` 模块级函数；`src/util/filename.py`：`sanitize_filename()` + `build_download_filename()`（`[标题](BV号).ext` 命名规则）+ `resolve_save_path()`。
- `src/models/`：`VideoInfo/VideoStat/VideoOwner/VideoUserAction/UserInfo` dataclass（`num_*` 命名已落实）。
- `src/services/`：包骨架。

### M2 已完成（2026-08-10）

- `src/models/download.py`：`VideoQuality` 枚举（qn 映射）、`DownloadResult`、`VideoStream`/`AudioStream`/`DashStreams`（DASH 流解析，`pick_video`/`best_audio` 选择逻辑）。
- `src/models/video.py`：`VideoInfo.from_view_json()`、`VideoStat.from_dict()`、`VideoOwner.from_view_dict()`。
- `src/util/downloader.py`：`download_stream`（流式下载 + 进度回调）、`merge_video_audio`（ffmpeg subprocess 列表参数）、`ffmpeg_available`（缓存探测）。
- `src/api/session.py`：新增 `get_raw()`（下载封面/媒体等非 JSON 资源）。
- `src/services/video.py`：`VideoService`——`fetch_info` / `fetch_tags` / `fetch_info_with_tags` / `get_playurl` / `download_video` / `download_audio` / `download_video_with_audio`（临时目录 + ffmpeg 合成 + 可保留音视频流）/ `download_cover`。下载命名接入 `build_download_filename`（`[标题](BV号).ext`），清晰度由 `VideoQuality` 枚举控制，失败抛异常。

### M2 验证结果（测试视频 BV1ov42117yC）

- `fetch_info`：标题/作者/统计/cid 全部正确。
- `fetch_tags`：10 个标签。
- `get_playurl`：12 路视频流 + 3 路音频流，`pick_video(P720)` 正确回退到最高可用流。
- 全链路下载验证：
  - 封面：`动画小剧场《补习部的一天》第4集：烟火(BV1ov42117yC).jpg`（142KB）
  - 音频：`...烟火(BV1ov42117yC).m4a`（4.9MB）
  - 合成：`...烟火(BV1ov42117yC).mp4`（18.4MB，ffprobe 验证时长 218s 正常）
- 错误路径：无效 BV 抛 `BiliAPIError`；缺 ffmpeg 抛 `FFmpegNotFoundError`；进度回调正常触发。

### M3 已完成（2026-08-10）

- `src/models/login.py`：`LoginUser`（nav 接口构造）。
- `src/services/login.py`：`LoginService`——`get_login_state`/`get_mid`/`get_uname`/`generate_qr`（返回 url+qrcode_key，二维码图片落盘）/`poll`（单次轮询，不阻塞）/`qr_login`（阻塞式完整流程，默认 60s 超时）/`save_cookie`（正则提取关键字段，刷新全局 cookie 缓存）。轮询与 UI 解耦。
- `src/models/history.py`：`HistoryItem`/`HistoryPage`（含游标 `has_more/max/business/view_at`）。
- `src/services/history.py`：`HistoryService`——`get_history_page`（统一分页器，替代旧代码复制三份的游标逻辑）/`get_history_all`/`get_invalid_video`（失效视频查找）/`save_video_history_df`（导出 xlsx，改为「输入 items 列表」而非内部串行拉详情）。构造函数不再发请求。
- `src/services/user.py`：`UserService`（改用无需风控参数的 card 接口）+ `ContractService`（老粉签约）。
- `src/services/reply.py`：`ReplyService.send_reply`（POST 构造，oid 自动由 BV 转 av）。
- `src/services/message.py`：`MessageService.send_msg`。
- `src/services/rank.py`：`RankService`（popular/ranking/new）。
- `src/services/fav.py`：`FavService.get_fav_bv`。
- `src/services/archive.py`：`ArchiveService`——旧 `seasons_archives_list` 接口已失效（一律 -400），改用 `seasons_series_list`（每条合集含完整视频列表）。
- 依赖补充：`openpyxl`（pandas 写 xlsx 必需，原项目缺失导致导出必失败），加入 requirements.txt。

### M3 验证结果

- `LoginService`：登录态正常（mid=506925078，uname=virtual小满）。
- `UserService`：card 接口取到「蔚蓝档案」（fans=3282822，level=6）。
- `RankService`：popular 3 条 / ranking 100 条。
- `HistoryService`：分页/多页/失效视频查找正常；导出 `output/history/test_history.xlsx` 成功（view_percent 计算正确：66.95%、100.00%）。
- `FavService`：默认收藏夹 175 个视频。
- `ArchiveService`：合集「明日方舟」6 个视频（新旧接口对比验证，旧接口 -400）。
- 写接口（评论/私信/签约）：用 mock 验证 POST 请求构造正确（oid/csrf/msg[] 字段齐全），**未发真实请求避免副作用**。
- 旧模块 + 新 services 全部可导入，compile 无警告。

### 下一步（M4/M5）

- **M4 前端对接**：新前端只依赖 `services` 层返回的 dataclass 与异常类型；约定 `progress_cb` 作为 UI 进度协议。

### M5 已完成（2026-08-10）

- 删除旧模块：`src/video.py`/`utils.py`/`history.py`/`login.py`/`up.py`/`archive.py`/`rank.py`/`reply.py`/`message.py` + `src/util/Colorful_Console.py`。
- `src/__init__.py`：导出全部新服务类 + `__version__`。
- 新建 `examples/quick_start.py`：旧 `main.py` 示例迁移为新 services 调用（含写操作警告注释）。
- 重写 `main.py`：简洁 CLI 入口（`info`/`video`/`cover`/`rank` 命令）。
- 重写 `README.md`：新结构/功能表/快速上手/测试说明。

### 测试搭建（2026-08-10）

- 新建 `tests/` 目录 + `pytest.ini`（注册 `network` 标记）+ `conftest.py`（路径注入、`--network` 开关、共享 fixture）。
- 单元测试（`-m "not network"`，不联网）：`test_bvid`/`test_filename`/`test_cookie`/`test_auth`/`test_errors`/`test_models`，共 57 个用例。
- 网络集成测试（`--network`）：`test_api_bilibili`（5 个）+ `test_services_bilibili`（13 个，含 P360 最小清晰度下载验证）。
- **测试结果**：单元 57 passed；网络 18 passed（默认被 skip）。
- 测试中发现并修复 2 个真实缺陷：`DashStreams` 构造时不排序（`best_video` 依赖外部排序）；`get_wbi(params)` 签名后 w_rid 未回写原 params（旧代码依赖该行为）。
- 安装 pytest 到 venv（未加入 requirements.txt，属于开发依赖，README 有说明）。

### 代码审查修复（2026-08-10）

对重构后代码做了系统审查，发现并修复以下问题：

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| 1 | **高** | `VideoQuality` 枚举 qn 值全部错配（P480=64、P720=74、HD1080P=120 等），与 BAC 文档不符；实际接口 id=80 是 1080P、id=64 是 720P | 按 BAC 文档重写：16=360P、32=480P、64=720P、74=720P60、80=1080P、112=1080P+、116=1080P60、120=4K、125=HDR、126=杜比、127=8K；新增排序断言测试 |
| 2 | **高** | `merge_video_audio` 的 ffmpeg 命令缺 `-y`，目标文件已存在时会**交互式挂起**（无 stdin 输入） | 加 `-y` + 输入文件存在性预检；加单测 |
| 3 | 中 | `download_video_with_audio` 不预检 ffmpeg，会先下载几十 MB 才报缺 ffmpeg | 下载前调用 `ffmpeg_available()` 预检 |
| 4 | 中 | `download_video/audio/with_audio` 各自重复 `fetch_info + get_playurl` | 抽 `_fetch_streams()` 共用 |
| 5 | 中 | `LoginService.qr_login` 的 `img_show` 打开 `save_cookie_path.with_suffix(".png")`，与 `generate_qr` 实际保存的 `QR_IMAGE_PATH` 不一致（自定义 cookie 路径时打开不存在的图） | 改为始终打开 `QR_IMAGE_PATH` |
| 6 | 中 | `HistoryItem.view_percent` 对负数 progress（除 -1 外）或无效 duration 计算错误 | 补 `progress < 0 or duration <= 0` 分支 |
| 7 | 低 | `BiliSession._request` 的 `except Exception: raise e` 冗余（等价裸 raise），业务错误与传输错误语义不清 | 移除冗余分支，明确重试仅针对传输层错误 |
| 8 | 低 | pyflakes：多处未使用导入 | 清理（`legacy_shim.py` 的再导出保留，属兼容意图） |

**验证**：单测 57→67（新增 downloader 9 个）；网络测试 18 全过；`python -m examples.quick_start` 全链路跑通（含真实评论/私信）；ffmpeg 二次合并验证 `-y` 生效。

---

## 八、接口使用示例（M2 定稿）

```python
from pathlib import Path
from src.services import VideoService
from src.models import VideoQuality

service = VideoService()  # 默认 cookie：assets/cookie/qr_login.txt

# 1. 获取视频信息（返回 VideoInfo 模型）
info = service.fetch_info("BV1ov42117yC")
print(info.title, info.owner.name, info.stat.num_dm)

# 2. 下载（默认存到 output/video/，文件名 [标题](BV号).扩展名）
r = service.download_video_with_audio("BV1ov42117yC", quality=VideoQuality.P1080)
print(r.path)  # output/video/动画小剧场《补习部的一天》第4集：烟火(BV1ov42117yC).mp4

# 3. 只下音频 / 封面，或指定目录
service.download_audio("BV1ov42117yC", Path("output/audio"))
service.download_cover("BV1ov42117yC", Path("output/cover"))

# 4. 进度回调
service.download_video("BV1ov42117yC", progress_cb=lambda done, total: print(done, total))

# 5. 多P视频（BV1Q43w6QETb 是 9 分P视频，含音频）
service.download_video_with_audio("BV1Q43w6QETb", page=2)   # 只下第2P，文件名 [标题]-P02-[part](BV号).mp4
service.download_all_pages("BV1Q43w6QETb")                   # 下载全部分P

# 6. 合集下载：bvid 或 sid 任选其一
service.download_season("BV1Q43w6QETb")                  # 从合集内任意一个视频进入
service.download_season(season_id=8683221)                # 按 sid 直接下载（洛天依·纯蓝幻乐）
service.download_season(season_id=1717000, mid=506925078) # 下载他人合集（明日方舟）
```

### 多P与合集下载（2026-08-10 扩展）

针对「分P视频」与「合集（season）」下载需求新增：

- **模型**：`VideoInfo.pages`（全部分P，`VideoPage`）、`VideoInfo.season`（所属合集，`VideoSeason`，含合集内全部稿件 `episodes`）。
- **分P下载**：`download_video/audio/video_with_audio` 新增 `page` 参数（指定第几P）；多P文件名 `[标题]-P{序号:02d}-[part](BV号).ext`（`build_multi_page_filename`）；`download_all_pages` 批量下载全部分P。
- **合集下载（bvid/sid 双通道）**：
  - `fetch_season(bvid=...)`：从合集内任意视频反查合集结构（`ugc_season`）；
  - `fetch_season(season_id=..., mid=...)`：按 sid 直接获取合集（`seasons_archives_list` 接口，需完整 `page_num`/`page_size` 参数；**不限登录用户**，任意 UP 主的合集都能查）；
  - `download_season(bvid=...)` / `download_season(season_id=...)`：下载整个合集，多P稿件逐P，保存到 `<dir>/<合集标题>/`。
- **接口修正**：`seasons_archives_list` 并非失效——缺 `page_num`/`page_size` 才返回 -400；`ArchiveService` 重写为按 sid 查询（可查他人合集，明日方舟 18 个稿件 vs 旧 `seasons_series_list` 只能查自己且分页不全）。
- **测试**：新增单测（多P/season 解析、分P文件名、fetch_season bvid/sid 双通道 mock）+ 网络测试（sid 获取合集、他人合集、分P音频下载）；实测 `download_season(season_id=1717000)` 下载明日方舟前 2 个稿件成功。

### 下载进度显示（2026-08-10 新增）

- 新增 `src/util/progress.py` 的 `BatchProgress`：批量下载进度，格式 `[i/n] [名字] [清晰度]: a/bMB (p%)`（`a` 已下载、`b` 总大小=各流 Content-Length 之和、`p` 百分比；无 Content-Length 时显示 `--%`）。
- 单视频（视频流+音频流+ffmpeg合成）字节跨流累计：视频/音频下载阶段显示字节进度，合成阶段单独状态提示。
- `download_all_pages` / `download_season` 自动创建共享 `BatchProgress` 驱动，无需手动传参；细粒度接口（`download_video/audio/video_with_audio/cover`）支持 `progress=` 参数传入。
- **清晰度标签**：进度条名称与 MB 之间显示实际清晰度（如 `[4K]`、`[1080P]`），来自 `VideoQuality.display_name`；显示的是**实际挑选出的流**清晰度（`from_qn` 映射，请求 HD4K 但只有 1080P 时显示 `[1080P]` 而非 `[4K]`）。

### 统一下载接口（2026-08-10 新增）

- `VideoService.download(bvid)`：**只接受 bvid** 的统一入口——属于合集则下载整个合集（含分P），否则下载该视频（含分P）；默认最高清晰度 HD4K；自动显示进度。
- 需要微调（清晰度/目录/单P等）的场景仍用细粒度接口（`download_video_with_audio(quality=...)` 等）。
- 实测 `service.download("BV1ov42117yC")` 进度正确输出（0.2/4.7MB (5.3%) → ... → 4.7/4.7MB (100.0%)）。

### 下载断点续传（2026-08-10 新增）

- `download_stream` 支持网络中断后的**断点续传**：中断（IncompleteRead/ConnectionError）时用 `Range` 头从已下载位置继续，默认最多重试 3 次。
- 实测：下载明日方舟合集视频时网络中断（读到 17MB），重试后续传完成，最终文件完整（79MB+76MB）。

### 清晰度语义（2026-08-10 设计确定）

`quality` 参数采用**精确目标**语义：

- **默认 `HD4K`（最高）**：不传 quality 时下载最高可用清晰度（4K→无4K自动回退）。
- **传具体档位 = 精确目标**：`P1080` 在有 4K 的视频上会下载 **1080P**（不会被拉到 4K）；`P720` 只下 720P。
- **匹配不到回退**：视频没有该档位（如请求 4K 但视频最高 1080P）时，回退到最高可用流。

`DashStreams.pick_video` 实现：先按降序精确匹配 `==quality` 的流，找不到则返回最高可用流。
实测（BV1ov42117yC，可用 360/480/720/1080 四档）：P360→360P、P480→480P、P720→720P、P1080→1080P、HD4K→1080P（回退）。

### 验证结果（测试视频 BV1ov42117yC）

- 旧模块 `src.video/utils/history/login/up/archive/rank/reply/message` 全部可导入（shim 生效）。
- `BiliSession.get(VideoUrls.VIEW)` 正常返回：标题「动画小剧场《补习部的一天》第4集：烟火」、up主「蔚蓝档案」、stat（view=818873 / dm=13235 / reply=1591）。
- DASH 流接口可拿到：12 路视频流 + 3 路音频流。
- `get_wbi()` 签名正常；`BV/AV` 往返一致；文件名生成符合 `[标题](BV号).mp4`。
- 错误体系验证：无效 BV 触发 `BiliAPIError`（code=-400），`raise_for_code(-101)` 触发 `BiliAuthError`。

### 下一步（M2 视频）

`VideoService`（`fetch_info` + `download_video`/`download_audio`/`download_video_with_audio`/`download_cover`），DASH 流解析与下载、ffmpeg 合并、`DownloadResult`，并接入 `build_download_filename` 命名规则。

