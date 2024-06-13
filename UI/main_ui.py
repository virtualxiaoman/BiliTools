from PyQt6.QtWidgets import QWidget, QLabel

from Tools import bili_tools as bt

class Win_Main(QWidget):
    def __init__(self):
        super().__init__()
        QLabel("这是主界面", self)
        self.setStyleSheet("background-color:lightblue;")
