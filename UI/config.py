import json
import os

class Config:
    config = None

    def __init__(self, config_path="data/ui_config.json"):
        self.config_path = config_path
        Config.config = self._load_config()

    # 在更新Config.config后，需要调用此函数更新json文件
    def update_config(self):
        # 将config写入self.config_path里
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(Config.config, f, ensure_ascii=False, indent=4)

    def _load_config(self):
        # 检查配置文件是否存在，不存在则创建
        if not os.path.exists(self.config_path):
            self.__init_json()
        with open(self.config_path, 'r', encoding='utf-8') as f:
            # 先检测是否是json文件，不是则初始化
            try:
                return json.load(f)
            except json.JSONDecodeError:
                self.__init_json()
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)

    def __init_json(self):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(
                {
                    "utils": {
                        "version": "0.0.2",
                        "author": "virtual小满",
                        "cookie_path": "cookie/qr_login.txt",
                        "qr_path": "cookie/qr_login.png"
                    },
                    "ui": {},
                    "main_ui": {},
                    "login_ui": {},
                    "download_ui": {
                        "video": {
                            "video_path": "output",
                            "video_name": "bv_special",
                            "video_add_desc": "视频(无音频)",
                            "audio_path": "output",
                            "audio_name": "title+bv",
                            "audio_add_desc": "音频",
                            "save_path": "output",
                            "save_name": "title+bv",
                            "save_add_desc": ""
                        },
                        "fav": {
                            "fav_path": "output"
                        }
                    }
                },
                f, ensure_ascii=False, indent=4)


# 常用颜色：
# 天依蓝66CCFF（102,204,255）
# 鹿乃FEE4D0（254,228,208）
# 初音绿39C5BB（57,197,187）
# 阿绫红EE0000（238,0,0）
# 南北组AA6680（170,102,128）
# 小满蓝B2D8E8（178,216,232）
# 粉色FFC0CB(255,192,203)
#
# 专业配色：
# https://element-plus.org/zh-CN/component/color.html
# https://www.materialui.co/colors
# https://www.materialpalette.com/
#
# 其他：
# 杏仁黄 FAF9DE (250, 249, 222)
# 胭脂红 FDE6E0 (253, 230, 224)
# 深绿 19CAAD (25, 202, 173)
# 浅绿 A0EEE1 (160, 238, 225)
# 浅蓝 BEE7E9 (190, 231, 233)
# 嫩绿 BEEDC7 (190, 237, 199)
# 深粉红 ECAD9E (236, 173, 158)
# 浅红 F4606C (244, 96, 108)

class Text:
    def __init__(self):
        self.WindowTitle = "BiliTools_V1.0"


class Background_css:
    def __init__(self):
        # 背景颜色
        self.WHITE = "background-color:white;"
        self.LIGHT_BLUE = "background-color: rgba(102, 204, 255, 0.2);"  # 天依蓝

class Button_css:
    def __init__(self):
        # 聚类算法得出阿洛娜浅蓝203 226 239 深蓝71 224 241，普拉娜浅紫238 228 241 深紫44 48 72
        # 淡蓝色+浅紫色边框，圆角，悬停时颜色变成淡蓝色的变体+浅紫色边框的变体
        self.BTN_ARONA = """
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
        QPushButton:pressed {
            background-color: rgba(203, 226, 239, 1);
            border-color: rgba(44, 48, 72, 1);
        }
        """
        # 上面这个颜色不适合白色背景，所以我自己调了一下QAQ
        self.BTN_BLUE_PURPLE = """
        QPushButton {
            background-color: rgba(71, 224, 241, 0.3);
            border: 2px solid rgba(206,147,216, 0.8);
            border-radius: 6px;
            padding: 4px 8px;
        }
        QPushButton:hover {
            background-color: rgba(203, 226, 239, 0.8);
            border-color: rgba(156,39,176, 0.6);
        }
        QPushButton:pressed {
            background-color: rgba(203, 226, 239, 1);
            border-color: rgba(156,39,176, 1);
        }
        """

class Input_css:
    def __init__(self):
        # 输入框样式，圆角，蓝色边框，悬停时颜色变成红色
        self.INPUT_BLUE_PURPLE = """
        QLineEdit {
            border: 2px solid rgba(64,158,255, 0.8);
            border-radius: 3px;
            padding: 2px 4px;
            color: rgba(51,126,204, 1);
            font-family: "Times New Roman";
            font-size: 16px;
            width: 300px;
        }
        
        QLineEdit:hover {
            border: 2px solid rgba(216,27,96, 0.6);
        }
        """

class Text_css:
    def __init__(self):
        # 文本样式，字体大小16px，黑色，粗体
        self.TEXT_BLACK_BOLD_16 = "font-size: 16px; color: black; font-weight: bold;"
        # 文本样式，字体大小16px，黑色
        self.TEXT_BLACK_16 = "font-size: 16px; color: black;"
        # 文本样式，字体大小16px，红色
        self.TEXT_RED_16 = "font-size: 16px; color: red;"
        # 文本样式，字体大小14px，黑色
        self.TEXT_BLACK_14 = "font-size: 14px; color: black;"
        # 文本样式，字体大小12px，灰色
        self.TEXT_GRAY_12 = "font-size: 12px; color: gray;"

class ComboBox_css:
    def __init__(self):
        # 下拉框样式，圆角，蓝色边框，悬停时颜色变成绿色
        self.COMBOBOX_BLUE_GREEN = """
        QComboBox {
            border: 2px solid rgba(206,147,216, 0.8);
            background-color: rgba(71, 224, 241, 0.3);
            border-radius: 3px;
            padding: 2px 4px;
        }
        
        QComboBox:hover {
            border: 2px solid rgba(149,212,117, 0.6);
        }
        """
