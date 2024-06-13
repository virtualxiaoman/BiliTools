from PyQt6.QtWidgets import QWidget, QLabel

class Win_Download(QWidget):
    def __init__(self):
        super().__init__()
        QLabel("下载界面", self)
        self.setStyleSheet("background-color:lightgreen;")


