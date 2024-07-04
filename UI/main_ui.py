from PyQt6.QtWidgets import QWidget, QLabel

from Tools import bili_tools as bt

class Win_Main(QWidget):
    def __init__(self):
        super().__init__()
        QLabel("一定要先登录后下载视频(未登录最多获取720P，而且我也没做未登录的功能，所以未登录的情况下进行操作会闪退！！！)\n", self)
        self.setStyleSheet("background-color:lightblue;")
