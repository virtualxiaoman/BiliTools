from PyQt6.QtWidgets import QWidget, QLabel

from Tools.bili_tools import biliLogin

class Win_Login(QWidget):
    def __init__(self):
        super().__init__()
        QLabel("这是登录界面", self)
        self.setStyleSheet("background-color:lightblue;")
        login_msg = biliLogin().get_login_state()
        login_msg = login_msg["data"]["isLogin"]
        print(login_msg)
        # if not login_msg:
        #     biliLogin().qr_login()
        #     QLabel("请扫描二维码", self)
        # else:
        #     print("已登录")
        #     QLabel("已登录", self)

