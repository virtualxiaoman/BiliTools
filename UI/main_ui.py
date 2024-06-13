from PyQt6.QtWidgets import QWidget, QLabel

from Tools import bili_tools as bt

class Win_Main(QWidget):
    def __init__(self):
        super().__init__()
        QLabel("先登录后下载视频(未登录最多获取720P，而且我也没做未登录的功能。。)", self)
        self.setStyleSheet("background-color:lightblue;")
