from PyQt6.QtWidgets import QWidget, QLabel

from Tools import bili_tools as bt

class Win_Main(QWidget):
    def __init__(self):
        super().__init__()
        QLabel("先登录后下载视频(未登录最多获取720P，而且我也没做未登录的功能。。)\n"
               "目前已经支持更改路径\n"
               "因为是多线程，在收藏夹下载完成时可能显示的进度不是n\\n的形式，暂时懒得管。"
               "另外，还没修复进度条的问题，虽然这不影响其功能", self)
        self.setStyleSheet("background-color:lightblue;")
