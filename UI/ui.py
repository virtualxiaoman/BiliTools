import sys
from PyQt6.QtWidgets import QApplication, QWidget, QMainWindow, QHBoxLayout, QVBoxLayout, QPushButton, QStackedLayout, QLabel

from UI.main_ui import Win_Main
from UI.download_ui import Win_Download
from UI.login_ui import Win_Login

from UI.config import Background_css
Background_css = Background_css()


class BiliTools_UI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.Layout_stack = None  # 抽屉布局器，存放的是切换显示的Widget

        self.create_stacked_layout()  # 堆叠布局
        self.init_menu()  # 菜单栏
        self.init_ui()  # 初始界面

    def create_stacked_layout(self):
        """ 创建堆叠布局(抽屉布局) """
        self.Layout_stack = QStackedLayout()
        # 创建单独的Widget
        win1 = Win_Main()
        win2 = Win_Download()
        win3 = Win_Login()
        # 将创建的2个Widget添加到抽屉布局器中
        self.Layout_stack.addWidget(win1)
        self.Layout_stack.addWidget(win2)
        self.Layout_stack.addWidget(win3)

    def init_ui(self):
        # 设置窗口的基础属性
        self.resize(1200, 700)
        self.setWindowTitle("BiliTools")
        self.setStyleSheet(Background_css.WHITE)

        # 窗口的中心部件，用来放置其他控件
        self.central_widget = QWidget()
        self.central_widget.setStyleSheet(Background_css.WHITE)
        self.setCentralWidget(self.central_widget)  # 将self.central_widget设置为窗口的中心部件。使得窗口内容将显示在其上
        # 创建整体的水平布局器
        H_Layout_main = self._init_H_Layout_main()
        # 设置当前要显示的Widget，从而能够显示这个布局器中的控件，类似于QWidget里的self.setLayout(container)
        self.centralWidget().setLayout(H_Layout_main)

    def init_menu(self):
        menu = self.menuBar()  # 调用父类中的 menuBar，从而对菜单栏进行操作
        menu.setNativeMenuBar(False)  # 是否依据本地化的菜单设置(比如 Mac 在顶部显示菜单栏)，False代表Mac也能和Windows一样在窗口里显示Menu
        file_menu = menu.addMenu("文件")
        file_menu.addAction("新建")
        file_menu.addAction("打开")
        file_menu.addAction("保存")
        edit_menu = menu.addMenu("编辑")
        edit_menu.addAction("复制")
        edit_menu.addAction("粘贴")
        tip_menu = menu.addMenu("提示(本菜单栏目前还没做功能)")

    def _init_H_Layout_main(self):
        # 1. 创建整体的水平布局器
        H_Layout_main = QHBoxLayout()
        # 2. 创建一个要显示具体内容的子Widget
        Widget_stack = self.__init_Widget_stack()
        # 3. 创建2个按钮，用来点击进行切换抽屉布局器中的widget
        Widget_btn = self.__init_Widget_btn()
        # 4. 将widget与btn添加到布局器中
        H_Layout_main.addWidget(Widget_btn)
        H_Layout_main.addWidget(Widget_stack)

        return H_Layout_main

    def __init_Widget_stack(self):
        Widget_stack = QWidget()
        Widget_stack.setLayout(self.Layout_stack)  # 设置为之前定义的抽屉布局
        Widget_stack.setStyleSheet(Background_css.WHITE)
        return Widget_stack

    def __init_Widget_btn(self):
        btn_widget = QWidget()
        btn_widget.setStyleSheet(Background_css.LIGHT_BLUE)
        VLayout_btn = QVBoxLayout()
        btn_press1 = QPushButton("主界面")
        btn_press2 = QPushButton("下载界面")
        btn_press3 = QPushButton("登录界面")
        # 添加点击事件
        btn_press1.clicked.connect(self.__switch_to_main)
        btn_press2.clicked.connect(self.__switch_to_download)
        btn_press3.clicked.connect(self.__switch_to_login)
        VLayout_btn.addWidget(btn_press1)
        VLayout_btn.addWidget(btn_press2)
        VLayout_btn.addWidget(btn_press3)
        VLayout_btn.addStretch(1)
        btn_widget.setLayout(VLayout_btn)
        return btn_widget

    def __switch_to_main(self):
        self.Layout_stack.setCurrentIndex(0)  # 设置抽屉布局器的当前索引值，即可切换显示哪个Widget

    def __switch_to_download(self):
        self.Layout_stack.setCurrentIndex(1)

    def __switch_to_login(self):
        self.Layout_stack.setCurrentIndex(2)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = BiliTools_UI()
    win.show()
    app.exec()
