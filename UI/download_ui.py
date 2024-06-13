import os

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit
from PyQt6.QtCore import QThread, pyqtSignal

from Tools.bili_tools import biliVideo

class DownloadThread(QThread):
    download_finished = pyqtSignal(bool)  # 定义一个信号，用于在下载完成时发射

    def __init__(self, bv_number, parent=None):
        super().__init__(parent)
        self.bv_number = bv_number
        print("初始化DownloadThread, bv_number:", bv_number)

    def run(self):
        # 下载视频
        print("开始下载视频")
        biliV = biliVideo(self.bv_number)
        success = biliV.download_video_with_audio(save_video_path='output', save_audio_path='output', save_path='output')
        print(f"视频下载：{success}")
        self.download_finished.emit(success)  # 发射信号


class Win_Download(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("下载界面")

        self.V_Layout_main = self._init_V_Layout_main()

        self.setLayout(self.V_Layout_main)

    def _init_V_Layout_main(self):
        V_Layout_main = QVBoxLayout()

        # 创建输入框&按钮的水平布局
        HLayout_input = self._init_HLayout_input()

        # 将水平布局添加到垂直布局中
        V_Layout_main.addLayout(HLayout_input)

        # 创建提示文本
        self.Label_download_tip = QLabel("输入BV号后，点击下载按钮开始下载")
        # 将提示文本添加到垂直布局中
        V_Layout_main.addWidget(self.Label_download_tip)
        V_Layout_main.addStretch(1)

        return V_Layout_main

    def _init_HLayout_input(self):
        HLayout_input = QHBoxLayout()
        # 创建提示文本
        Label_bv_prompt = QLabel("输入BV号：")
        # 创建输入框
        self.Line_bv_input = QLineEdit()
        # 创建下载按钮
        btn_download = QPushButton("下载")
        btn_download.clicked.connect(self.on_download_clicked)  # 连接点击事件到处理函数
        # 将提示文本和输入框添加到水平布局中
        HLayout_input.addWidget(Label_bv_prompt)
        HLayout_input.addWidget(self.Line_bv_input)
        HLayout_input.addStretch(1)
        HLayout_input.addWidget(btn_download)
        HLayout_input.addStretch(10)
        return HLayout_input

    def on_download_clicked(self):
        # 获取用户输入的内容
        bv_number = self.Line_bv_input.text()
        self.bv = bv_number
        if not self.bv:
            print("用户未输入BV号")
            self.Label_download_tip.setText(f"不输入BV号那下载个锤子啊！")
        # 不是12位的字符串或者不是BV,bv开头就不合法
        elif not (isinstance(self.bv, str) and len(self.bv) == 12 and (self.bv.startswith("BV") or self.bv.startswith("bv"))):
            print("用户输入的BV号不合法")
            self.Label_download_tip.setText(f"输入的BV号不合法，请检查后重新输入")
        else:
            print("用户输入的BV号为：", self.bv)
            self.Label_download_tip.setText(f"正在下载{self.bv}")
            if os.path.exists(f"output/{self.bv}视频.mp4"):
                print("视频已经存在，不再下载")
                self.Label_download_tip.setText("视频已经存在，不需要再次下载")
            else:
                self.download_thread = DownloadThread(self.bv)
                self.download_thread.download_finished.connect(self.on_download_finished)
                self.download_thread.start()

    def on_download_finished(self, success):
        if not success:
            print("下载失败")
            self.Label_download_tip.setText("下载失败，一般是因为视频失效了，小概率是其他原因")
        else:
            print("下载完成")
            self.Label_download_tip.setText("已经下载完毕。"
                                            "提示：下载的视频和音频将保存在output文件夹中（目前默认就这样，我现在懒得优化）")
