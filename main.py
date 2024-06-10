# Author: virtual小满
# BiliTools是一个py操控B站的小工具
# 示例代码一般以BV1ov42117yC为例。up主：蔚蓝档案；视频：动画小剧场《补习部的一天》第4集：烟火


from Tools.bili_tools import biliVideo

class Example:
    def __init__(self):
        pass

    @staticmethod
    def download_video():
        biliV = biliVideo("BV1ov42117yC")
        biliV.download_video(save_video_path="output")

    @staticmethod
    def download_audio():
        biliV = biliVideo("BV1ov42117yC")
        biliV.download_audio(save_audio_path="output")

    @staticmethod
    def download_video_with_audio():
        biliV = biliVideo("BV16m4y1p7PB")
        biliV.download_video_with_audio(save_video_path='output', save_audio_path='output', save_path='output')


if __name__ == '__main__':
    quick_start = Example()  # 这是一个快速开始示例
    quick_start.download_video()  # 下载视频BV1ov42117yC到output文件夹里
    quick_start.download_audio()  # 下载音频BV1ov42117yC到output文件夹里
    quick_start.download_video_with_audio()  # 下载视频BV1ov42117yC到output文件夹里


