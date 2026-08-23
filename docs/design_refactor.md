# BiliTools 代码整洁与模块化重构报告

> 审查日期：2026-08-23  
> 审查范围：`src/`、`frontend/pyside6/`、`tests/`、`main.py` 及直接调用链  
> 目标：在保持现有公开行为、下载规则、异常语义、进度事件和 GUI 流程不变的前提下，提高可读性、可测试性和复用性。

## 1. 结论摘要

当前项目已经具备较好的基础分层：

- `src/models/` 使用 `dataclass` 表达视频、流、下载结果等领域数据；
- `src/urls/` 集中维护 API 地址；
- `src/api/session.py` 统一请求、Cookie、重试和业务错误处理；
- `src/util/downloader.py` 已使用 `.part` 文件、原子替换、取消事件和 ffmpeg 进程管理；
- `frontend/pyside6/` 已将窗口、页面、组件、worker 和任务管理器拆开。

因此，本次不建议推倒重写，而应继续收敛职责和输入契约。主要维护成本集中在：

1. `src/services/video.py` 同时处理 API、模型转换、流选择、文件命名、单文件下载、批量编排、并发、风控和日志，文件达到 1141 行；
2. `DownloadPanel` 与 `DownloadWorker` 使用裸 `dict` 传递任务规格，字段和默认值分散在 UI 与 worker 两侧；
3. 收藏夹、合集、UP 主三条批量链路存在高度相似的列表获取、目录创建、进度、账号分配、并发和汇总逻辑；
4. `AccountManager` 同时处理 JSON 持久化、文件锁、Cookie、账号选择、登录接入和全局生效路径；
5. `DownloadManager` 通过多个平行字典维护一个任务生命周期，状态清理与 Qt 信号转发耦合较深。

建议采用**渐进式重构**：先引入类型化边界和可复用组件，再迁移实现；保留旧入口作为兼容包装，不直接改变 GUI、CLI 和 SDK 调用方式。

> 本文档同时记录已落地的第一阶段重构。实施过程保留了当前工作区已有的业务修复，并通过兼容入口避免改变 GUI、CLI 和 SDK 的调用方式。尚未迁移的部分继续作为后续渐进式重构候选。

### 第一阶段已实施

- 新增 `src/models/download_request.py`，以 `DownloadRequest`、`DownloadSource` 和 `MediaType` 统一下载任务输入，并保留旧字典规格转换。
- `DownloadManager.submit()` 和 `DownloadWorker` 在边界统一转换请求；短链仍在 Worker 线程内解析，旧的 `spec` 读取入口继续可用。
- `DownloadWorker._execute()` 改为来源处理器注册表，视频、收藏夹、合集、UP 主、表情包、装扮和收藏集分别由小型私有方法负责。
- `DownloadManager` 使用 `TaskRecord` 维护任务、去重键和完成状态，保持原有 Qt 信号与线程释放时序。
- `VideoService` 抽取 `_download_bvid_collection()`，统一收藏夹与 UP 主的并发、风险门禁、账号轮询、结果顺序和会话清理。
- 使用项目虚拟环境执行非网络回归测试：`203 passed, 27 deselected`。

## 2. 当前问题审查

### 2.1 复杂度热点

| 文件/位置 | 现状 | 影响 |
|---|---|---|
| `src/services/video.py:108` | 一个类覆盖查询、下载和批量编排；`download_fav`、`download_season`、`download_up` 均为 100 行级流程 | 修改下载选项时回归范围大 |
| `src/services/video.py:156-189` | `get_playurl()` 同时负责参数构造、WBI 签名、响应校验和模型构造 | API 适配与领域选择逻辑难以独立测试 |
| `src/services/archive.py:25-150`、`:152-312` | 分页和合集解析主要使用原始 `dict`，方法过长，并保留注释掉的旧实现 | 数据变化容易造成隐式字段错误 |
| `src/util/downloader.py:106-231` | Range、重试、取消、`.part` 文件、进度和响应关闭集中在一个函数 | 网络策略与文件提交策略无法独立复用 |
| `frontend/pyside6/widgets/download_panel.py:71-224` | 构造函数承担控件、布局、默认值和信号绑定 | UI 修改影响多个状态边界 |
| `frontend/pyside6/widgets/download_panel.py:342-418` | 多个来源重复构造任务字典 | 字段增删容易产生来源间不一致 |
| `frontend/pyside6/workers/download_worker.py:77-236` | `_execute()` 用长条件分支处理全部下载来源 | 新增来源必须修改核心流程 |
| `frontend/pyside6/workers/download_manager.py:20-168` | 多个字典共同维护同一任务 | 生命周期状态容易漏清理 |
| `src/services/account.py:98-394` | 账号仓储、锁、Cookie、登录接入和切换集中在一个类 | 存储和账号策略无法独立替换或测试 |

### 2.2 主要可维护性问题

#### 任务规格没有类型契约

`DownloadPanel._build_spec()` 返回裸字典，`DownloadWorker` 再按字符串读取 `source`、`media_type`、`quality`、`threads`、`cache_dirs`、`force` 等字段。拼写错误只能在运行时暴露，且 UI、worker、manager 都必须知道内部字段名。

#### 批量流程重复

`download_fav`、`download_season`、`download_up` 都重复执行：解析 ID、获取列表、决定目录、创建进度、选择顺序/并发、分配账号、处理风控、展平结果和输出汇总日志。重复逻辑会导致缓存、进度或错误修复在不同入口之间漂移。

#### 原始类型泄漏到服务层

虽然 `VideoInfo`、`VideoPage`、`VideoSeason` 已经提供了领域模型，但服务层仍有较多 `list`、`dict`、`Any` 和 `Optional[list]`。原始 API 字典应限制在 API 适配器或模型工厂边界内。

#### 旧实现残留

`src/services/archive.py:255-262` 保留整段注释掉的旧实现。源码只应保留当前路径和必要行为说明，旧代码交由 Git 历史保存。

## 3. 目标架构

```text
frontend / CLI / examples
        │ 只构造请求对象、订阅进度、展示结果
        ▼
application
        │ 编排用例：单视频、批量下载、登录、切换账号
        ▼
domain models + ports
        │ VideoInfo、DownloadRequest、DownloadResult、Protocol
        ▼
adapters / infrastructure
        │ BiliSession、B 站 URL、JSON、requests、ffmpeg、文件系统
```

建议在现有目录上渐进增加：

```text
src/
├── models/                 # 领域数据和值对象
├── api/                    # HTTP、鉴权、错误映射
├── urls/                   # API 地址
├── services/               # 对外兼容 facade
├── application/            # 下载/账号用例编排（新增）
├── ports/                  # Protocol 接口（新增）
└── util/                   # 纯函数与基础设施适配
```

依赖规则：

1. `models` 不依赖 `services`、`frontend`、`requests` 或 PySide6；
2. `api` 负责网络和错误，不负责文件命名或 Qt 信号；
3. `application` 依赖模型和接口，通过构造函数接收具体实现；
4. `services` 作为稳定 SDK facade 调用 application，不让 application 反向依赖具体 service；
5. `frontend` 只依赖 facade、DTO 和进度事件，不读取后端私有状态；
6. 网络、ffmpeg、文件写入继续全部在 Qt 工作线程执行。

## 4. 可复用单元与重构策略

### 4.1 引入类型化下载请求

`DownloadPanel._build_spec()` 在 `:342-396` 和 `:398-418` 反复构造字典；`DownloadWorker` 再通过字符串键解释这些字段。建议新增 `src/models/download_request.py`：

```python
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class DownloadSource(StrEnum):
    VIDEO = "bv"
    FAVORITE = "fav"
    SEASON = "season"
    UPLOADER = "up"
    EMOTE = "emote"
    GARB = "garb"
    DRESSUP = "dressup"


class MediaType(StrEnum):
    VIDEO = "video_with_audio"
    AUDIO = "audio"


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    source: DownloadSource
    input_value: object
    save_dir: Path
    media_type: MediaType = MediaType.VIDEO
    quality: VideoQuality = VideoQuality.HD4K
    scope: str = "all"
    page: int = 1
    threads: int = 1
    distribute_accounts: bool = False
    cache_dirs: tuple[Path, ...] = field(default_factory=tuple)
    force: bool = False
    pending_resolve: bool = False

    def deduplication_key(self) -> tuple:
        return (self.source, repr(self.input_value), self.scope, self.page,
                self.media_type, self.quality, self.save_dir)
```

兼容迁移方式：

- 保留 `_build_spec()` 作为过渡入口，但立即转换为 `DownloadRequest`；
- `DownloadManager.submit()` 暂时同时接受旧 `dict` 和新对象，统一调用 `from_legacy_dict()`；
- 枚举值保持现有字符串不变，避免影响日志、任务去重和后端分支；
- 完成迁移后，再删除内部的裸字典兼容代码。

这样可以统一默认值，并把任务去重从 manager 内部的 `repr(spec["input"])` 提升为请求对象的稳定行为。

### 4.2 提取视频媒体流水线

`VideoService` 同时负责 API 读取、响应解析、分P选择、清晰度回退、文件命名、缓存路径、流下载、ffmpeg 合成、批量并发、账号分配、风控和日志。建议拆成：

1. `VideoCatalog`：`fetch_info()`、`fetch_tags()`、`get_playurl()`，只返回 `VideoInfo` / `DashStreams`；
2. `StreamSelector`：根据 `VideoQuality` 选择视频和音频流；
3. `MediaPathResolver`：根据标题、BV 号、分P和扩展名生成目标路径并查缓存；
4. `MediaDownloadPipeline`：执行“缓存检查 → 临时下载 → 合成/提交 → `DownloadResult`”；
5. `BatchDownloadCoordinator`：负责列表批量、顺序/并发、风险门禁、结果顺序和汇总；
6. `VideoService`：保留现有公开方法，作为 facade 组合以上对象。

当前 `get_playurl()` 中的原始 JSON 到 `VideoStream`/`AudioStream` 转换也应移入 `DashStreams.from_api_response()`，这样响应校验可以脱离完整 service 单独测试。

对外方法签名继续兼容，例如 `download_video_with_audio()`、`download_all_pages()` 等只负责把旧参数转换为 request，再委托给流水线。

### 4.3 统一收藏夹、合集、UP 主批量编排

三类批量任务只有“列表来源”和“目录命名”不同，下载执行过程相同。可定义：

```python
@dataclass(frozen=True, slots=True)
class BatchDownloadPlan:
    label: str
    items: Sequence[DownloadItem]
    save_dir: Path
    media_type: MediaType
    quality: VideoQuality
    threads: int
    cache_dirs: tuple[Path, ...]
    force: bool


class BatchItemSource(Protocol):
    def load(self) -> BatchDownloadPlan: ...


class BatchDownloadCoordinator:
    def execute(self, plan: BatchDownloadPlan) -> list[DownloadResult]: ...
```

分别实现 `FavoriteItemSource`、`SeasonItemSource`、`UploaderItemSource`，它们只负责取得并规范化列表；`BatchDownloadCoordinator` 统一处理：

- 进度对象创建；
- 顺序/并发选择；
- `RiskGate` 和 `AccountSessionPool`；
- 不可见视频跳过；
- 输入顺序不变的结果返回；
- 每个视频完成时的汇总日志；
- finally 中关闭由 coordinator 创建的 session。

现有 `_parallel_run()` 可保留为底层执行器，并补充泛型类型标注。这样可以消除三条批量链路中的重复闭包、计数器和结果展平逻辑。

### 4.4 解耦账号持久化与账号策略

`AccountManager` 既知道 JSON 格式，又知道锁、Cookie 文件路径、当前账号、默认账号、登录响应解析和在线查询昵称。建议拆为：

1. `AccountRepository`：读写 `accounts.json`，负责 schema 校验、原子写入和跨进程锁；
2. `CookieStore`：保存、读取、刷新和清理 Cookie 文件；
3. `AccountSelector`：实现“默认账号优先、当前账号次之”的选择规则；
4. `AccountSessionProvider`：从可用账号生成独立 `BiliSession`，供并发下载分流；
5. `AccountManager`：保留 facade，仅编排登录、切换、删除等用例。

登录接入仍维持当前顺序：先写 Cookie，再登记账号，再切换生效路径，再查询昵称；该顺序属于行为不变量，不能在重构中改变。

### 4.5 将 worker 条件分支改为处理器注册表

`DownloadWorker._execute()` 通过 `if src == ...` 分流视频、收藏夹、合集、UP 主、表情和装扮。建议定义：

```python
class DownloadHandler(Protocol):
    def execute(self, request: DownloadRequest, context: WorkerContext) -> DownloadPayload: ...
```

注册表可映射：

```python
handlers = {
    DownloadSource.VIDEO: VideoDownloadHandler,
    DownloadSource.FAVORITE: FavoriteDownloadHandler,
    DownloadSource.SEASON: SeasonDownloadHandler,
    DownloadSource.UPLOADER: UploaderDownloadHandler,
    DownloadSource.EMOTE: EmoteDownloadHandler,
    DownloadSource.GARB: GarbDownloadHandler,
    DownloadSource.DRESSUP: DressupDownloadHandler,
}
```

worker 只负责线程生命周期、取消、异常分类、日志和 Qt 信号；具体业务由 handler 完成。新增来源只增加 handler 和注册项，符合开闭原则，也能单独测试每个来源。

### 4.6 简化 `DownloadManager` 任务状态

当前 manager 使用多个字典维护同一任务的不同索引。建议引入：

```python
@dataclass
class TaskRecord:
    task_id: int
    deduplication_key: tuple
    worker: DownloadWorker
    done_emitted: bool = False
```

manager 内部只保留 `tasks_by_id: dict[int, TaskRecord]` 和 `task_id_by_key: dict[tuple, int]`。worker 到 task id 的映射优先通过信号携带 task id，而不是依赖 `sender()` 和动态属性 `_download_task_id`；若必须保留 `sender()`，也应把动态属性访问封装在 `TaskRecord` 内。

任务状态可以明确为 `QUEUED`、`RUNNING`、`SUCCEEDED`、`FAILED`、`CANCELLED`、`FINISHED`，但对外继续保持现有 `task_started`、`task_progress`、`task_phase`、`task_finished` 信号语义。

### 4.7 拆分下载基础设施

`src/util/downloader.py` 当前行为较完整，但可细化为：

- `FFmpegResolver`：PATH 和 `imageio-ffmpeg` 探测；
- `ResumableStreamDownloader`：Range、`.part`、重试、取消和进度；
- `AtomicFileCommitter`：大小校验和 `os.replace()`；
- `MediaMerger`：ffmpeg 参数、超时、取消和临时输出；
- 保留 `download_stream()`、`merge_video_audio()` 作为兼容 facade。

必须保持：正式文件不会被失败下载覆盖；Range 被忽略时从头开始；`.part` 不作为缓存命中；取消事件能中断流下载和 ffmpeg；进度回调参数顺序不变。

## 5. 命名与现代 Python 语法

### 5.1 命名建议

| 当前名称 | 建议名称 | 原因 |
|---|---|---|
| `dir` | `save_dir` | 明确是保存目录 |
| `mode` | `media_type` | 表达视频/音频业务语义 |
| `bvids` | `video_bvids` | 明确集合存放 BV 号 |
| `ep` | `episode` | 避免缩写，批量逻辑更易读 |
| `p` | `page` | 与 `VideoPage` 概念一致 |
| `n` | `item_count` / `file_count` | 区分项目数和文件数 |
| `fn` | `action` / `download_item` | 表达回调职责 |
| `spec` | `request` | 表达跨层请求契约 |
| `e` | `error` / `exception` | 便于异常处理阅读 |
| `up_name` | `uploader_name` | 与领域命名保持一致 |
| `VideoStream.video` | `video_streams` | 与 `audio_streams` 对称 |

已有 `VideoStat.num_view`、`num_dm`、`num_reply` 等命名方向应继续保持；API 缩写只允许出现在 `from_dict()` 适配边界内。

### 5.2 适合采用的 Python 3.11+ 特性

- `StrEnum`：替代 `source`、`media_type` 等散落字符串；
- `dataclass(frozen=True, slots=True)`：用于请求、计划、任务记录等值对象；
- `Protocol`：为 `SessionPort`、`AccountRepository`、`DownloadHandler`、`BatchItemSource` 定义最小接口；
- 内置泛型：使用 `list[VideoStream]`、`dict[str, object]`、`Callable[[int, int], None]`；
- `ExceptionGroup` 仅在需要汇总多个并发失败时使用，默认不要改变现有“首个异常上抛”行为；
- `match` 只用于稳定的枚举分派，不要用它掩盖过长的业务逻辑。

不建议为了“现代化”强行引入异步 HTTP、全局依赖注入容器或复杂事件总线；当前 Qt worker + requests 的运行模型已经稳定，重点应是职责边界而不是更换运行时。

## 6. SOLID 原则审查

### 单一职责原则（SRP）

- 将 `VideoService` 拆成查询、流选择、媒体流水线和批量编排；
- 将 `AccountManager` 拆成仓储、Cookie 存储和账号策略；
- 将 `DownloadWorker` 拆成线程壳与业务 handler；
- 将 `DownloadManager` 拆成任务状态与 Qt 生命周期协调。

### 开闭原则（OCP）

- 通过 `DownloadHandler` 注册表新增下载来源，不修改 worker 主流程；
- 通过 `BatchItemSource` 新增收藏夹、合集或未来播放列表来源；
- 通过 `MediaMerger` 接口支持其他合成后端，不修改视频下载用例。

### 里氏替换原则（LSP）

- `SessionPort` 实现都必须返回相同的业务 `data` 语义和错误映射；
- 测试 double 与真实 `BiliSession` 都应支持最小的 `get`、`post`、`get_raw`、`close` 契约；
- 账号 session provider 返回的 session 必须具备独立 Cookie 和可关闭生命周期。

### 接口隔离原则（ISP）

不要让下载 handler 依赖包含全部 service 方法的“大接口”。建议拆为：

- `VideoCatalogPort`：信息与播放流；
- `MediaDownloaderPort`：流下载和合成；
- `AccountSessionPort`：获取/释放 session；
- `ProgressSink`：进度、阶段和完成事件。

### 依赖倒置原则（DIP）

`BatchDownloadCoordinator` 不应直接创建 `BiliSession`、`RiskGate` 或 `ThreadPoolExecutor`；这些对象由组装层注入，生产环境使用真实实现，测试环境使用 fake。`VideoService` 当前直接导入 `ArchiveService`，应改为注入 `ArchiveCatalogPort`，降低 service 间的直接依赖。

## 7. 功能守恒约束

重构过程中必须将以下内容视为不可变的外部契约。

### SDK 与 CLI

- `VideoService.fetch_info()` 仍返回 `VideoInfo`；
- `download_video_with_audio()`、`download_audio()`、`download_cover()`、`download_all_pages()`、`download_season()`、`download_fav()`、`download_up()` 的现有参数和默认值保持兼容；
- `main.py` 的命令名称、参数含义和退出行为不改变；
- 旧调用传入字符串 `mode`、`Path`、`str` 目录仍可用。

### 文件与缓存

- 默认输出目录、子目录命名、文件名规则、扩展名推断保持不变；
- 缓存命中与 `force=True` 的覆盖语义保持不变；
- `.part` 临时文件、原子提交和失败清理规则保持不变；
- 账号 Cookie 路径迁移与自定义路径保留现有行为。

### GUI

- 输入继续支持 BV/av/完整 URL、短链、收藏夹、合集和 UP 主；
- 短链解析继续在 worker 线程进行，不能回到 UI 线程同步请求；
- 任务去重键的业务组成不改变；
- Qt 信号名称、参数数量和“任务完成后再释放 worker”的生命周期规则保持不变；
- 下载取消、窗口关闭等待、登录失效跳转和风控提示保持不变。

### 并发与风控

- 顺序下载与并发下载的结果列表仍按输入顺序返回；
- `RiskGate` 仍在风控后协调线程暂停；
- 多账号分流仍按轮询策略分配独立 session；
- 由 service 创建的 session 仍在 finally 中关闭；
- 单个视频不可见时批量任务继续跳过并记录日志，其余异常仍按现有错误分类处理。

## 8. 测试与验证策略

### 8.1 先建立行为基线

在迁移实现前，先固定现有行为：

```powershell
python -m compileall src frontend tests
pytest tests/ -m "not network"
```

当前测试已经覆盖账号、下载器、模型、进度、前端路由和服务缓存，应继续以这些测试作为安全网，不用真实网络测试替代单元测试。

### 8.2 按模块增加纯单元测试

1. `DownloadRequest`：默认值、旧字典转换、规范化和去重键；
2. `StreamSelector`：精确清晰度、无权限时最高可用回退、空流错误；
3. `MediaPathResolver`：单P、多P、非法字符、扩展名和缓存目录优先级；
4. `BatchDownloadCoordinator`：顺序/并发、输入顺序、不可见跳过、风控重试和 session 关闭；
5. `AccountRepository`：损坏 JSON、并发保存、原子替换和默认账号选择；
6. handler registry：每个来源只验证请求如何转换为 service 调用；
7. `TaskRecord`：重复完成信号、异常退出和 shutdown 清理。

### 8.3 验收指标

- `src/services/video.py` 主类控制在约 300 行以内，单个方法原则上不超过 40 行；
- GUI 构造函数只负责组装，单个 `_build_*` 方法不超过 50 行；
- 新增下载来源只需新增 handler/source adapter 和注册项，不修改 worker 主循环；
- 服务层不再接收未说明的裸 `dict`，API 原始字典仅存在于 `api` 或模型工厂边界；
- 非网络测试全部通过，现有公开入口回归测试通过；
- 使用 `git diff --check` 检查空白和换行问题；
- 至少保留一组兼容测试，验证旧字典请求、旧 service 构造方式和旧 CLI 命令仍可用。

## 9. 推荐实施顺序

### 阶段一：只加类型边界，不改流程

1. 新增 `DownloadSource`、`MediaType`、`DownloadRequest`；
2. 给 `DownloadRequest` 增加旧字典转换；
3. 修改 panel/manager/worker 在边界处转换；
4. 为 `VideoQuality`、流列表、进度回调补齐类型标注；
5. 跑完整非网络回归测试。

### 阶段二：提取无副作用组件

1. 从 `VideoService` 提取 `StreamSelector`、`MediaPathResolver`；
2. 从 `downloader.py` 提取 `FFmpegResolver` 和 `AtomicFileCommitter`；
3. 从 `archive.py` 提取分页器和模型工厂；
4. 删除注释掉的旧实现，保留 Git 历史；
5. 保留旧函数作为兼容包装。

### 阶段三：统一批量下载编排

1. 定义 `BatchDownloadPlan` 和 `BatchItemSource`；
2. 迁移合集链路；
3. 迁移收藏夹链路；
4. 迁移 UP 主链路；
5. 比较每个入口的日志、进度、结果顺序和异常行为。

### 阶段四：解耦账号和 worker

1. 提取 `AccountRepository`、`CookieStore`、`AccountSessionProvider`；
2. 引入 handler registry；
3. 用 `TaskRecord` 替换 manager 的平行字典；
4. 收敛 Qt 信号和任务状态；
5. 删除已无调用方的兼容内部字段。

### 阶段五：清理与文档

1. 更新 `README.md` 的模块图和 SDK 示例；
2. 为新增 Protocol 和请求对象补充开发文档；
3. 检查 `src/` 中的裸 `dict`、泛化 `list` 和过长方法；
4. 运行格式、编译和非网络测试；
5. 以小提交方式合并，每个阶段独立可回滚。

## 10. 总结

本项目不需要通过更换框架来获得可维护性，核心是把已有能力重新放回清晰边界：

- **请求对象**负责表达意图；
- **模型**负责表达数据；
- **API 适配器**负责网络和响应错误；
- **单文件流水线**负责媒体文件；
- **批量协调器**负责并发、风控和进度；
- **账号组件**负责持久化与 session 生命周期；
- **worker/manager**只负责线程与 Qt 生命周期；
- **service facade**负责保持旧 API 兼容。

按上述顺序渐进实施，可以在不改变下载结果、缓存语义、进度事件、账号切换和 GUI 操作方式的前提下，显著降低单个模块的认知负担，并为未来接入 Web、CLI 批处理或新的 B 站内容类型留下稳定扩展点。
