import os
import time

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from Tools.bili_tools import biliLogin
from Tools.config import useragent
from Tools.config import bilicookies as cookies

from UI.config import Config, Button_css

UI_Config = Config()
Button_css = Button_css()

# 扫码登录
class LoginThread(QThread):
    login_finish_state = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.cookie_path = UI_Config.config["utils"]["cookie_path"]

    def run(self):
        # 扫码登录，登录cookie存入COOKIE_PATH
        login_success = biliLogin().qr_login(img_show=False, full_path=self.cookie_path)  # 返回登录结果, True of False
        self.login_finish_state.emit(login_success)

# 检查登录状态
class CheckLoginThread(QThread):
    login_state = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.cookie_path = UI_Config.config["utils"]["cookie_path"]

    def run(self):
        # 检查登录状态
        if not os.path.exists(self.cookie_path):
            self.login_state.emit(False)
        else:
            headers = {
                "User-Agent": useragent().pcChrome,
                "Cookie": cookies(path=self.cookie_path).bilicookie,
                'referer': "https://www.bilibili.com"
            }
            login_msg = biliLogin(headers).get_login_state()  # 获取登录信息
            login_state = login_msg["data"]["isLogin"]  # True or False
            self.login_state.emit(login_state)

# 检查是否请求到二维码
class CheckQRLoginThread(QThread):
    qrcode_state = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.qr_path = UI_Config.config["utils"]["qr_path"]

    def run(self):
        # 一直检查本地是否有二维码图片，有则返回True
        while not os.path.exists(self.qr_path):
            print("等待二维码图片生成...")
            time.sleep(0.5)
        self.qrcode_state.emit(True)

# 界面
class Win_Login(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.cookie_path = UI_Config.config["utils"]["cookie_path"]
        self.qr_path = UI_Config.config["utils"]["qr_path"]

    def init_ui(self):
        self.setWindowTitle("登录界面")
        self.V_Layout_main = self._init_V_Layout_main()

        self.setLayout(self.V_Layout_main)
        # self.show()  # 显示窗口

    # 登录线程
    def init_check_login_thread(self):
        self.Thread_check_login = CheckLoginThread()
        self.Thread_check_login.login_state.connect(self.__on_login_state_checked)
        self.Thread_check_login.start()

    def _init_V_Layout_main(self):
        V_Layout_main = QVBoxLayout()
        self.H_Layout_login = self._init_HLayout_login()
        V_Layout_main.addLayout(self.H_Layout_login)

        # 二维码图片
        self.Label_qr_code = QLabel("[调试信息]此处是二维码图片(如果需要二维码登录的话会显示在这里)")

        V_Layout_main.addWidget(self.Label_qr_code)
        V_Layout_main.addStretch(1)
        return V_Layout_main

    def _init_HLayout_login(self):
        H_Layout_login = QHBoxLayout()
        # 登录提示信息
        self.Label_login_tip = QLabel("点击右侧按钮以检查登录状态--->")
        self.Label_login_tip.setStyleSheet("font-size: 12px; color: black;"
                                           "background-color: pink;")
        # 创建一个按钮，连接init_login_thread
        self.Button_login = QPushButton("点击检查状态")
        self.Button_login.setStyleSheet(Button_css.BTN_BLUE_PURPLE)
        self.Button_login.clicked.connect(self.init_check_login_thread)

        H_Layout_login.addWidget(self.Label_login_tip)
        H_Layout_login.addStretch(1)
        H_Layout_login.addWidget(self.Button_login)
        H_Layout_login.addStretch(20)
        return H_Layout_login

    def _show_qr_code(self):
        # 加载二维码图片
        qr_code_pixmap = QPixmap(self.qr_path)

        # 设置 QLabel 的尺寸为图片的尺寸
        self.Label_qr_code.setPixmap(qr_code_pixmap)
        self.Label_qr_code.setFixedSize(300, 300)
        self.Label_qr_code.setScaledContents(True)  # 自适应图片大小

        # 向 V_Layout_main 中添加 QLabel 控件
        self.V_Layout_main.addWidget(self.Label_qr_code)

    # 扫码登录完成后的回调函数
    def __on_login_finished(self, success_qr_login):
        if success_qr_login:
            # 扫码登录成功
            print("[__on_login_finished]登录成功")
            self.Label_login_tip.setText("已登录(扫码登录成功)")
            # 删除二维码图片
            if os.path.exists(self.qr_path):
                os.remove(self.qr_path)
            # 删除界面上的二维码图片
            self.Label_qr_code.clear()
        else:
            print("[__on_login_finished]登录失败，请重试（目前没写重试功能，需要重启程序）")
            self.Label_login_tip.setText("登录失败，请重试（目前没写重试功能，因为一般不会有这个错误。如果需要重新登录，需要重启程序）")

    # 检查本地是否已经登录，如果已经登录则显示已登录，否则显示未登录并生成二维码
    def __on_login_state_checked(self, success_local):
        if success_local:
            # 本地cookie文件存在且有效
            print("[__on_login_state_checked]已登录")
            self.Label_login_tip.setText("已登录(本地已有登录信息)")
        else:
            print("[__on_login_state_checked]未登录")
            self.Label_login_tip.setText("尚未登录，请扫描二维码登录")
            # 删除过时的二维码图片与cookie文件
            if os.path.exists(self.qr_path):
                os.remove(self.qr_path)
            if os.path.exists(self.cookie_path):
                os.remove(self.cookie_path)
            # 重新登录
            self.Thread_login = LoginThread()
            self.Thread_login.login_finish_state.connect(self.__on_login_finished)
            self.Thread_login.start()

            # 显示二维码
            self.Thread_check_qr = CheckQRLoginThread()
            self.Thread_check_qr.qrcode_state.connect(self._show_qr_code)
            self.Thread_check_qr.start()



