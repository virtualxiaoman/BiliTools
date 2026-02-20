# Author: virtual小满
# BiliTools是一个py操控B站的小工具
# 示例代码一般以视频BV1ov42117yC为例。up主：蔚蓝档案。标题：动画小剧场《补习部的一天》第4集：烟火


from src.bili_tools import BiliVideo, BiliLogin, biliMessage


class Example:
    def __init__(self):
        pass

    @staticmethod
    def login_qr():
        biliLogin = BiliLogin()
        biliLogin.qr_login(full_path="./assets/cookie/qr_login.txt")

    @staticmethod
    def download_video():
        biliV = BiliVideo("BV1ov42117yC")
        biliV.download_video(save_video_path="output")

    @staticmethod
    def download_audio():
        biliV = BiliVideo("BV1ov42117yC")
        biliV.download_audio(save_audio_path="output")

    @staticmethod
    def download_video_with_audio():
        biliV = BiliVideo("BV1ov42117yC")
        biliV.download_video_with_audio(save_video_path='output', save_audio_path='output', save_path='output')

    @staticmethod
    def send_message():
        biliM = biliMessage()
        biliM.send_msg(506925078, 3493133776062465, "催更[doge]")


if __name__ == '__main__':
    # pass
    # 这是一个快速开始示例，请依次取消下面的注释，运行即可
    quick_start = Example()
    # quick_start.login_qr()  # 扫码登录，登录成功后会在assets/cookie/qr_login.txt里保存cookie信息
    # # quick_start.download_video()  # 下载视频BV1ov42117yC到output文件夹里
    # # quick_start.download_audio()  # 下载音频BV1ov42117yC到output文件夹里
    # quick_start.download_video_with_audio()  # 下载视频BV1ov42117yC到output文件夹里
    quick_start.send_message()  # 给up主381978872发送消息，内容是"催更[doge]"
