## 一、项目描述
**通过代码运行(src)**：`main.py`提供了quickstart，亦可通过查看函数里的注释来运行项目中的各个功能。

**构建UI项目(UI)**：运行`UI/ui.py`。或者使用`pyinstaller -F --noconsole UI/ui.py`构建项目。如需图标，请使用`pyinstaller -F --noconsole --icon=UI/data/arona.ico UI/ui.py`

**注意**：UI项目依赖于src项目，但是src项目不依赖于UI项目。同样的，src项目与UI的config相互独立。因为src是方便开发者使用的，而UI界面是方便普通用户使用的。

### 1.1 功能
本项目是py操控bilibili的工具，目前主要实现了以下功能：
1. 下载b站视频
2. 在评论区留言
3. 私信
4. 扫码登录
5. 获取收藏夹信息
如果你只需要实现基本功能，**只需**查看`main.py`或者单独查看每个类对应的函数的注释即可，或者使用`release`中发布的.exe程序，以下内容无需过多关注。

### 1.2 项目依赖
- 本项目依赖以下库：`pandas, request`。
个人建议使用`ffmpeg`，如果没有`ffmpeg`，可以在[ffmpeg官网](https://ffmpeg.org/download.html)下载，然后将ffmpeg.exe放到系统环境变量中。
可以参考视频[BV1qw4m1d7hx](https://www.bilibili.com/video/BV1qw4m1d7hx/)。 注：原先音视频合成的`moviepy`代码已经删除，现**仅可使用**`ffmpeg`进行音视频合成。

### 1.3 项目结构
本项目BiliTools的结构如下：
```
.
├── src                             # BiliTools主要的功能代码
│   ├── cookie
│   │   └── qr_login.txt              # (默认名称，需要自行填写)扫码登录后的cookie
│   ├── util                          # 工具类
│   │   └── Colorful_Console.py       # 让控制台能彩色输出
│   ├── bili_tools.py                 # 本项目的主要功能
│   ├── bili_util.py                  # bili_tools所依赖的底层工具
│   ├── config.py                     # 配置文件，主要是cookie与user-agent
│
├── UI                                # BiliTools的UI，还未开发
│   ├── cookie
│   │   └── qr_login.txt              # (默认名称，需要自行填写)扫码登录后的cookie
│   ├── data
│   │   ├── BG_CS_S1Final_24_5.jpg    # 启动界面图片
│   │   └── ui_config.json            # UI的配置文件
│   ├── config.py                     # 默认配置文件，主要是样式与文本
│   ├── download_ui.py                # 下载视频
│   ├── login_ui.py                   # 登录
│   ├── main_ui.py                    # 主界面
│   ├── ui.py                         # UI的入口
│
├── main.py                           # BiliTools的Tools的快速上手
```
目前UI项目的配置文件等路径信息不够好，后续会进行优化。

## 二、使用说明
### 2.1 src的使用方法
如项目描述所述，可以通过`main.py`、注释等来使用项目中的各个功能。
其中介绍一下通过历史记录导出用户喜好的方法：
通过`save_video_history_df`导出的df的属性有：

`bv, progress, duration, view_percent, view_time, u_like, u_coin, u_fav, u_score, title, view, dm ,reply, time, like, coin ,fav, share, tag, tid, up_name, up_follow, up_followers`

解释如下：

|    英文属性名     |       中文解释        |
|:------------:|:-----------------:|
|      bv      |    视频bv号(唯一ID)    |
|   progress   |       观看进度        |
|   duration   |       视频时长        |
| view_percent |     观看进度的百分比      |
|  view_time   |  观看时间(表格按时间降序排列)  |
|    u_like    |       用户点赞数       |
|    u_coin    |       用户投币数       |
|    u_fav     |       用户收藏数       |
|   u_score    | 用户评分(点赞+硬币数+2*收藏) |
|    title     |       视频标题        |
|     view     |       观看次数        |
|      dm      |       弹幕数量        |
|    reply     |       评论数量        |
|     time     |       发布时间        |
|     like     |        点赞数        |
|     coin     |        投币数        |
|     fav      |        收藏数        |
|    share     |        分享数        |
|     tag      |        标签         |
|     tid      |      视频分区tid      |
|   up_name    |       up昵称        |
|  up_follow   |      是否关注up       |
| up_followers |       up粉丝数       |

### 2.2 UI的使用方法
UI项目需要运行`UI/ui.py`。
ui_config.json是UI的配置文件，可以自行修改。具体解释如下：
```
{
    // 项目的主要信息
    "utils": {
        "version": "0.0.2",                      // 项目版本(这个不是UI窗口的标题)
        "author": "virtual小满",                 // 作者
        "cookie_path": "cookie/qr_login.txt",    // cookie的路径
        "qr_path": "cookie/qr_login.png"         // 二维码的路径
    },
    
    // 项目的整体UI配置
    "ui": {},
    
    // 主界面的配置
    "main_ui": {},
    
    // 登录界面的配置
    "login_ui": {},
    
    // 下载界面的配置
    "download_ui": {
        // 单个视频下载的配置(add_desc参数暂时无效)
        // video是无音频的视频，audio是音频，save是合成后的音视频
        // path是保存路径，name是名称，add_desc是额外信息，最后的路径是path+name+add_desc+默认的文件后缀名
        // name非真实名称，只是一个标识。"bv"表示名称是其bv号，"title"表示名称是其标题，"title+bv"表示名称是标题加bv号
        // 在UI界面里，三个path是绑定更改的。audio_name与save_name是绑定的。
        "video": {
            "video_path": "output",
            "video_name": "bv",                 // 该参数不支持在UI界面中修改
            "video_add_desc": "视频(无音频)",    // 该参数不支持在UI界面中修改
            "audio_path": "output",
            "audio_name": "bv",
            "audio_add_desc": "音频",           // 该参数不支持在UI界面中修改
            "save_path": "output",
            "save_name": "title+bv",
            "save_add_desc": ""
        },
        // 收藏夹的配置
        "fav": {
            "fav_path": "output"                // 收藏夹的保存路径
        }
    }
}
```