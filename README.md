## 一、项目描述
通过代码运行：main.py提供了quickstart，亦可看函数里的注释。

构建UI项目：`pyinstaller -F --noconsole UI/ui.py`

### 1.1 功能
本项目是py操控bilibili的工具，目前主要实现了以下功能：
1. 下载bilibili视频
2. 在评论区留言
3. 私信
4. 扫码登录
5. 获取收藏夹信息

### 1.2 项目依赖
- 本项目依赖以下库：`pandas, request, moviepy`

其中`moviepy`非必须，个人建议使用`ffmpeg`（然后将音视频合成的`moviepy`代码注释掉），不然视频音频合成的时候比较慢。

如果没有ffmpeg，可以在[ffmpeg官网](https://ffmpeg.org/download.html)下载，然后将ffmpeg.exe放到系统环境变量中。
可以参考视频[BV1qw4m1d7hx](https://www.bilibili.com/video/BV1qw4m1d7hx/)

### 1.3 项目结构
本项目BiliTools的结构如下：
```
.
├── Tools                             # BiliTools主要的功能代码
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
│   │   └── BG_CS_S1Final_24_5.jpg    # 启动界面图片
│   ├── config.py                     # 配置文件，主要是样式与文本
│   ├── download_ui.py                # 下载视频
│   ├── login_ui.py                   # 登录
│   ├── main_ui.py                    # 主界面
│   ├── ui.py                         # UI的入口
│
├── main.py                           # BiliTools的入口，暂时没做，请运行bili_tools.py
```
