class Text:
    def __init__(self):
        self.WindowTitle = "BiliTools_V0.1(测试版)"


class Background_css:
    def __init__(self):
        # 背景颜色
        self.WHITE = "background-color:white;"
        self.LIGHT_BLUE = "background-color: rgba(102, 204, 255, 0.2);"  # 天依蓝

class Button_css:
    def __init__(self):
        # 按钮样式，淡蓝色+浅紫色边框，圆角，悬停时颜色变成淡蓝色的变体+浅紫色边框的变体
        # 聚类算法得出阿洛娜浅蓝203 226 239 深蓝71 224 241，普拉娜浅紫238 228 241 深紫44 48 72
        self.BTN_BLUE_PURPLE = """
        QPushButton {
            background-color: rgba(71, 224, 241, 0.3);
            border: 2px solid rgba(238, 228, 241, 1);
            border-radius: 6px;
            padding: 4px 8px;
        }
        QPushButton:hover {
            background-color: rgba(203, 226, 239, 0.8);
            border-color: rgba(44, 48, 72, 0.6);
        }
        """
