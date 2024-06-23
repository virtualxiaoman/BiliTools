import os
import re
import time
import random
import requests
import threading
from functools import partial

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QFileDialog, QComboBox
from PyQt6.QtCore import QThread, pyqtSignal, Qt

from Tools.bili_tools import biliVideo, biliFav, biliLogin
from Tools.bili_util import BV2AV
from Tools.config import useragent

from UI.config import Config, Button_css, Input_css, Text_css, ComboBox_css
Button_css = Button_css()
Input_css = Input_css()
Text_css = Text_css()
ComboBox_css = ComboBox_css()
UI_Config = Config()  # 更新时必须是更新UI_Config，这样才能保证config是最新的

class DownloadThread(QThread):
    # 定义一个信号，用于在下载完成时发射：
    # bool下载是否成功，str提示语类型tip_type，tuple当前下载的进度current_process， strBV号，str下载格式down_type
    download_finished = pyqtSignal(bool, str, tuple, str, str)

    def __init__(self, bv_number, down_type, tip_type, current_process=(1, 1), parent=None):
        super().__init__(parent)
        self.video_config = UI_Config.config["download_ui"]["video"]
        self.bv_number = bv_number  # 视频BV号
        self.down_type = down_type  # 下载类型(视频va、音频audio)
        self.tip_type = tip_type  # 提示语类型(视频video、收藏夹fav)
        self.current_process = current_process  # 当前下载的进度，默认是(1, 1)，其余时候是(i, N), i=1~N

    def run(self):
        print(f"开始下载{self.down_type}，BV号：{self.bv_number}")
        biliV = biliVideo(self.bv_number)
        success = False
        if biliV.accessible is False:
            self.download_finished.emit(False, self.tip_type, self.current_process, self.bv_number, self.down_type)
        else:
            if self.down_type == 'va':
                success = biliV.download_video_with_audio(
                    save_video_path=self.video_config["video_path"],
                    save_video_name=self.get_name(self.bv_number, self.video_config["video_name"]),
                    save_video_add_desc=self.video_config["video_add_desc"],
                    save_audio_path=self.video_config["audio_path"],
                    save_audio_name=self.get_name(self.bv_number, self.video_config["audio_name"]),
                    save_audio_add_desc=self.video_config["audio_add_desc"],
                    save_path=self.video_config["save_path"],
                    save_name=self.get_name(self.bv_number, self.video_config["save_name"]),
                    save_add_desc=self.video_config["save_add_desc"]
                )
            elif self.down_type == 'audio':
                success = biliV.download_audio(
                    save_audio_path=self.video_config["audio_path"],
                    save_audio_name=self.get_name(self.bv_number, self.video_config["audio_name"]),
                    save_audio_add_desc=self.video_config["audio_add_desc"])
            print(f"下载结果：{success}")
            self.download_finished.emit(success, self.tip_type, self.current_process, self.bv_number, self.down_type)  # 发射信号

    def get_name(self, bv_number, name_type):
        """
        获取文件名
        :param bv_number: bv号
        :param name_type: "bv"表示名称是其bv号，"title"表示名称是其标题，"title+bv"表示名称是标题加bv号
        :return:
        """
        if name_type == 'bv':
            return bv_number
        elif name_type == 'title':
            biliV = biliVideo(bv_number)
            biliV.get_content()
            title = biliV.title
            title = re.sub(r'[\\/:*?"<>|]', '', title)  # 检查title中是否有不能作为文件名的字符
            title = re.sub(r'\s+', '', title)  # 因为ffmpeg不支持，所以去除所有空白字符，包括空格、制表符等
            # title = re.sub(r'[&$、()]', '', title)  # ffmpeg不支持这些字符，测试视频是BV1VjgkebEZc。补充：经过修复，只要在命令时加上""即可。
            print(f"获取到的标题为：{title}")
            return title
        elif name_type == 'title+bv':
            return f"{self.get_name(bv_number, 'title')}({bv_number})"
        # bv_special仅能由合成音频前的那个没有音频的视频使用，为了防止文件名相同导致出错
        elif name_type == 'bv_special':
            return f"{bv_number}视频(bv_special)"
        else:
            return bv_number

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
                "Cookie": open(self.cookie_path, "r").read(),
                'referer': "https://www.bilibili.com"
            }
            login_msg = biliLogin(headers).get_login_state()  # 获取登录信息
            login_state = login_msg["data"]["isLogin"]  # True or False
            self.login_state.emit(login_state)

class Win_Download(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("下载界面")
        self.V_Layout_main = self._init_V_Layout_main()
        self.setLayout(self.V_Layout_main)

    def _init_V_Layout_main(self):
        V_Layout_main = QVBoxLayout()

        # 创建检查登录信息的文本
        self.__init_Label_login_check()

        # 创建选择文件夹按钮
        HLayout_btn_video_choice = self.__init_HLayout_btn_video_choice()

        # 创建视频下载的输入框&按钮的水平布局
        HLayout_video = self._init_HLayout_video()
        # 创建提示文本
        self.Label_download_video_tip = QLabel("输入BV号后，点击下载按钮开始下载")
        self.Label_download_video_tip.setStyleSheet(Text_css.TEXT_GRAY_12)

        # 创建收藏夹下载的输入框&按钮的水平布局
        HL_fav = self._init_HLayout_fav()
        # 创建提示文本
        self.Label_download_fav_tip = QLabel("输入收藏夹fid后，点击下载按钮开始下载")
        self.Label_download_fav_tip.setStyleSheet(Text_css.TEXT_GRAY_12)

        V_Layout_main.addWidget(self.Label_login_check)
        V_Layout_main.addStretch(1)
        V_Layout_main.addLayout(HLayout_btn_video_choice)
        V_Layout_main.addStretch(2)
        V_Layout_main.addLayout(HLayout_video)
        V_Layout_main.addWidget(self.Label_download_video_tip)
        V_Layout_main.addStretch(1)
        V_Layout_main.addLayout(HL_fav)
        V_Layout_main.addWidget(self.Label_download_fav_tip)
        V_Layout_main.addStretch(50)
        return V_Layout_main

    # 视频下载的水平布局
    def _init_HLayout_video(self):
        HLayout_video = QHBoxLayout()

        # 创建提示文本
        Label_bv_prompt = QLabel("视频BV号：")
        Label_bv_prompt.setStyleSheet(Text_css.TEXT_BLACK_16)

        # 创建输入框
        self.Line_bv_input = QLineEdit()
        self.Line_bv_input.setStyleSheet(Input_css.INPUT_BLUE_PURPLE)
        self.Line_bv_input.setPlaceholderText("bv, av, url")
        self.Line_bv_input.setToolTip("支持bv、av、网址的输入")

        # 创建下载按钮
        btns_download = self.__init_Widget_btn_video_download()

        HLayout_video.addWidget(Label_bv_prompt)
        HLayout_video.addWidget(self.Line_bv_input)
        HLayout_video.addStretch(1)
        HLayout_video.addWidget(btns_download)
        HLayout_video.addStretch(10)
        return HLayout_video

    # 收藏夹下载的水平布局
    def _init_HLayout_fav(self):
        HL_fav = QHBoxLayout()

        # 创建提示文本
        Label_fav_prompt = QLabel("收藏夹FID：")
        Label_fav_prompt.setStyleSheet(Text_css.TEXT_BLACK_16)

        # 创建输入框
        self.Line_fav_input = QLineEdit()
        self.Line_fav_input.setStyleSheet(Input_css.INPUT_BLUE_PURPLE)
        self.Line_fav_input.setPlaceholderText("fid")
        self.Line_fav_input.setToolTip("支持fid或收藏夹链接的输入")

        # 创建下载按钮
        btns_download = self.__init_Widget_btn_fav()

        HL_fav.addWidget(Label_fav_prompt)
        HL_fav.addWidget(self.Line_fav_input)
        HL_fav.addStretch(1)
        HL_fav.addWidget(btns_download)
        HL_fav.addStretch(10)
        return HL_fav

    # 选择文件夹按钮的水平布局
    def __init_HLayout_btn_video_choice(self):
        HLayout_btn = QHBoxLayout()

        # 创建一个下拉菜单，提示语是文件名，选择的选项有1.bv号 2.标题 3.标题+bv号
        self.Label_combo_tip = QLabel("文件名：")
        self.Label_combo_tip.setStyleSheet(Text_css.TEXT_BLACK_16)
        # self.Label_combo_tip.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)  # 设置居左对齐

        # 创建下拉菜单
        self.combo_box = QComboBox(self)
        self.combo_box.addItem("标题+bv号")
        self.combo_box.addItem("标题")
        self.combo_box.addItem("bv号")
        self.combo_box.setStyleSheet(ComboBox_css.COMBOBOX_BLUE_GREEN)
        self.combo_box.setToolTip("选择保存的文件名格式")
        self.combo_box.currentIndexChanged.connect(self.__on_video_name_combobox_changed)

        # 创建选择文件夹按钮
        btn_choice = QPushButton("选择文件夹")
        btn_choice.setStyleSheet(Button_css.BTN_BLUE_PURPLE)
        btn_choice.clicked.connect(self.__on_choice_video_folder)

        # 创建文件夹路径显示文本
        self.Label_video_path = QLabel(
            f"当前路径：{self.__shorten_folder_path(UI_Config.config['download_ui']['video']['save_path'])}")
        self.Label_video_path.setStyleSheet(Text_css.TEXT_GRAY_12)

        HLayout_btn.addWidget(self.Label_combo_tip)
        HLayout_btn.addWidget(self.combo_box)
        HLayout_btn.addStretch(1)
        HLayout_btn.addWidget(btn_choice)
        HLayout_btn.addWidget(self.Label_video_path)
        HLayout_btn.addStretch(20)

        return HLayout_btn

    # 创建检查登录信息的文本
    def __init_Label_login_check(self):
        self.Label_login_check = QLabel("检查登录信息中...")
        self.Label_login_check.setStyleSheet(Text_css.TEXT_BLACK_16)
        # 检查登录状态
        self.check_login_thread = CheckLoginThread()
        self.check_login_thread.login_state.connect(self.__on_login_state)
        self.check_login_thread.start()

    # 创建下载按钮-视频
    def __init_Widget_btn_video_download(self):
        btn_widget = QWidget()
        HLayout_btn = QHBoxLayout()
        # 创建下载按钮
        btn_download = QPushButton("下载视频")
        btn_download.setStyleSheet(Button_css.BTN_BLUE_PURPLE)
        btn_download.clicked.connect(partial(self.__on_download_video_clicked, down_type='va'))
        # 创建下载音频按钮
        btn_download_audio = QPushButton("下载音频")
        btn_download_audio.setStyleSheet(Button_css.BTN_BLUE_PURPLE)
        btn_download_audio.clicked.connect(partial(self.__on_download_video_clicked, down_type='audio'))
        HLayout_btn.addWidget(btn_download)
        HLayout_btn.addWidget(btn_download_audio)
        btn_widget.setLayout(HLayout_btn)
        return btn_widget

    # 创建下载按钮-收藏夹
    def __init_Widget_btn_fav(self):
        btn_widget = QWidget()
        HLayout_btn = QHBoxLayout()
        # 创建下载视频按钮
        btn_download = QPushButton("下载视频")
        btn_download.setStyleSheet(Button_css.BTN_BLUE_PURPLE)
        btn_download.clicked.connect(partial(self.__on_download_fav_clicked, down_type='va'))
        # 创建下载音频按钮
        btn_download_audio = QPushButton("下载音频")
        btn_download_audio.setStyleSheet(Button_css.BTN_BLUE_PURPLE)
        btn_download_audio.clicked.connect(partial(self.__on_download_fav_clicked, down_type='audio'))
        HLayout_btn.addWidget(btn_download)
        HLayout_btn.addWidget(btn_download_audio)
        btn_widget.setLayout(HLayout_btn)
        return btn_widget

    # 检查登录状态
    def __on_login_state(self, login_state):
        if login_state:
            self.Label_login_check.setText("登录状态：已登录")
            self.Label_login_check.setStyleSheet(Text_css.TEXT_BLACK_16)
        else:
            self.Label_login_check.setText("登录状态：未登录")
            self.Label_login_check.setStyleSheet(Text_css.TEXT_RED_16)

    # 下载视频
    def __on_download_video_clicked(self, down_type):
        # 获取用户输入的内容
        bv_number = self.Line_bv_input.text()
        self.bv = self.__transform_bv(bv_number)
        self.down_type = down_type
        if not self.__check_bv(self.bv):
            return
        else:
            print("[__on_download_video_clicked]用户输入的BV号为：", self.bv)
            self.Label_download_video_tip.setText(f"正在下载{self.bv}")
            if down_type == 'va' and self.__check_video_exist(self.bv):
                print("[__on_download_video_clicked]视频已经存在，不再下载")
                self.Label_download_video_tip.setText(f"视频{self.bv}已经存在，不需要再次下载")
            elif down_type == 'audio' and self.__check_audio_exist(self.bv):
                print("[__on_download_video_clicked]音频已经存在，不再下载")
                self.Label_download_video_tip.setText(f"音频{self.bv}已经存在，不需要再次下载")
            else:
                self.download_thread = DownloadThread(self.bv, down_type, 'video')
                self.download_thread.download_finished.connect(self.__on_download_finished)
                self.download_thread.start()
            # if os.path.exists(f"output/{self.bv}视频.mp4"):
            #     print("视频已经存在，不再下载")
            #     self.Label_download_video_tip.setText("视频已经存在，不需要再次下载")
            # else:
            #     self.download_thread = DownloadThread(self.bv)
            #     self.download_thread.download_finished.connect(self.__on_download_finished)
            #     self.download_thread.start()

    # 文件名格式下拉菜单改变
    def __on_video_name_combobox_changed(self, index):
        name_type = self.combo_box.currentText()
        if name_type == "标题+bv号":
            name_type = "title+bv"
        elif name_type == "标题":
            name_type = "title"
        else:
            name_type = "bv"
        UI_Config.config["download_ui"]["video"]["audio_name"] = name_type
        UI_Config.config["download_ui"]["video"]["save_name"] = name_type
        UI_Config.update_config()
        print(f"[__on_video_name_combobox_changed]选择的文件名格式为：{name_type}")

    # 选择文件夹
    def __on_choice_video_folder(self):
        initial_path = UI_Config.config["download_ui"]["video"]["save_path"]
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹", initial_path)
        if folder:
            folder = os.path.normpath(folder)
            UI_Config.config["download_ui"]["video"]["video_path"] = folder
            UI_Config.config["download_ui"]["video"]["audio_path"] = folder
            UI_Config.config["download_ui"]["video"]["save_path"] = folder
            UI_Config.update_config()

            print(len(folder))
            folder_show = self.__shorten_folder_path(folder)  # 如果folder太长，只显示最后一部分
            print(f"[__on_choice_video_folder]选择的文件夹为：{folder}")
            print(f"[__on_choice_video_folder]显示的文件夹为：{folder_show}")
            self.Label_video_path.setText(f'当前路径：{folder_show}')
        else:
            print("[__on_choice_video_folder]未选择文件夹")

    # 下载收藏夹视频
    def __on_download_fav_clicked(self, down_type):
        fid = self.Line_fav_input.text()

        self.fid = self.__transform_fav(fid)
        self.down_type = down_type  # 下载类型：视频va/音频audio
        bv_count = 0  # 需要下载的视频数量（也就是去掉已经下载的视频）

        # 获取fid对应的bv列表
        if not self.__check_fav(self.fid):
            return False
        print("[__on_download_fav_clicked]用户输入的收藏夹FID为：", self.fid)  # 如2525700378
        self.Label_download_fav_tip.setText(f"正在获取收藏夹{self.fid}的视频BV号，别急")
        biliF = biliFav()
        bvids = biliF.get_fav_bv(self.fid)
        if bvids is None:
            self.Label_download_fav_tip.setText(f"获取收藏夹{self.fid}的视频BV号失败，可能是你没有访问权限，请注意是否登录的是收藏夹所属账号")
            return False
        print(bvids)

        # 准备下载
        self.Label_download_fav_tip.setText(f"正在准备下载，共有{len(bvids)}个视频需要下载")

        videos_to_download = []
        for i, bvid in enumerate(bvids):
            if down_type == 'va' and self.__check_video_exist(bvid):
                print(f"视频{bvid}已经存在，不再下载")
                self.Label_download_fav_tip.setText(f"视频{bvid}已经存在，不需要再次下载")
            elif down_type == 'audio' and self.__check_audio_exist(bvid):
                print(f"音频{bvid}已经存在，不再下载")
                self.Label_download_fav_tip.setText(f"音频{bvid}已经存在，不需要再次下载")
            else:
                videos_to_download.append(bvid)
        bv_count = len(videos_to_download)

        # 开始下载
        if bv_count == 0:
            if down_type == 'va':
                self.Label_download_fav_tip.setText(f"收藏夹{self.fid}的视频已经全部存在，不需要再次下载")
            else:
                self.Label_download_fav_tip.setText(f"收藏夹{self.fid}的音频已经全部存在，不需要再次下载")
        else:
            download_thread = threading.Thread(target=self.__start_fav_download_threads,
                                               args=(videos_to_download, down_type, bv_count))
            download_thread.start()
            self.Label_download_fav_tip.setText(f"线程已经全部开始，共有{bv_count}个视频需要下载")

    # 收藏夹下载线程
    def __start_fav_download_threads(self, videos_to_download, down_type, bv_count):
        folder = UI_Config.config["download_ui"]["video"]["save_path"]
        folder_show = self.__shorten_folder_path(folder)
        self.download_thread = []
        for i, bvid in enumerate(videos_to_download):
            self.download_thread_i = DownloadThread(bvid, down_type, 'fav', (i + 1, bv_count))
            self.download_thread_i.download_finished.connect(self.__on_download_finished)
            self.download_thread.append(self.download_thread_i)
            self.download_thread[i].start()  # 开始下载
            time.sleep(random.uniform(0.2, 0.5))  # 防止请求过快导致封号

        # 等待所有线程完成
        for i in range(bv_count):
            self.download_thread[i].wait()

        time.sleep(1)  # 等待1秒，防止界面显示不及时而被其他的地方修改了self.Label_download_fav_tip的内容
        print("[__start_fav_download_threads]所有线程已经完成")
        self.Label_download_fav_tip.setText(f"收藏夹{self.fid}的视频已经全部下载完毕，共有{bv_count}个视频，保存在'{folder_show}'里")

    # 单个视频(无论是普通视频还是收藏夹的视频都是这个)下载完成后的回调函数
    def __on_download_finished(self, success, tip_type, current_process, bv_number, download_type):
        if download_type == "va":
            download_type = "视频"
        else:
            download_type = "音频"
        if not success:
            print("下载失败")
            if tip_type == 'video':
                self.Label_download_video_tip.setText(f"当前进度：{current_process[0]}/{current_process[1]}。"
                                                      f"{download_type}{bv_number}下载失败，一般是因为视频失效了，小概率是其他原因")
            elif tip_type == 'fav':
                self.Label_download_fav_tip.setText(f"当前进度：{current_process[0]}/{current_process[1]}。"
                                                    f"收藏夹{download_type}{bv_number}下载失败，一般是因为视频失效了，小概率是其他原因")
            else:
                self.Label_download_video_tip.setText(f"当前进度：{current_process[0]}/{current_process[1]}。"
                                                      f"[代码进入错误路径]请注意tip_type的值，当前{download_type}{bv_number}下载失败")
        else:
            print("下载完成")
            folder = UI_Config.config["download_ui"]["video"]["save_path"]
            folder_show = self.__shorten_folder_path(folder)
            if tip_type == 'video':
                if current_process == (1, 1):
                    self.Label_download_video_tip.setText(f"{download_type}{bv_number}已经下载完毕。"
                                                          f"提示：{download_type}保存在{folder_show}里")
                else:
                    self.Label_download_video_tip.setText(f"当前进度：{current_process[0]}/{current_process[1]}，{download_type}{bv_number}。"
                                                          f"提示：{download_type}保存在{folder_show}里")
            elif tip_type == 'fav':
                if current_process == (1, 1):
                    self.Label_download_fav_tip.setText(f"收藏夹{download_type}{bv_number}已经下载完毕。"
                                                        f"提示：收藏夹{self.fid}的{download_type}保存在'{folder_show}'里")
                else:
                    self.Label_download_fav_tip.setText(f"当前进度：{current_process[0]}/{current_process[1]}，收藏夹{download_type}{bv_number}。"
                                                        f"提示：收藏夹{self.fid}的{download_type}保存在'{folder_show}'里")
            else:
                self.Label_download_video_tip.setText(f"[代码进入错误路径]请注意tip_type的值，当前视频{bv_number}下载成功")

    # 转换bv输入框的内容为bv号
    def __transform_bv(self, bvORav):
        """
        输入bv, av, url，返回得到的bv号或False。
        返回的bv号不一定是准确的，需要self.__check_bv
        False代表转化过程中已经存在问题
        """
        # 如果以av,AV开头，则提取后面的数字部分，然后转换成BV
        if bvORav.startswith("av") or bvORav.startswith("AV"):
            bvORav = bvORav[2:]
            if not bvORav.isdigit():
                print("[__transform_bv]用户输入的AV号不合法")
                self.Label_download_video_tip.setText(f"输入的AV号不合法，请检查后重新输入")
                return False
            bv = BV2AV().av2bv(bvORav)
            return bv
        # 如果以bv,BV开头，则直接返回即可（检查部分请在__check_bv中进行）
        elif bvORav.startswith("bv") or bvORav.startswith("BV"):
            return bvORav
        # 如果含有http，尝试访问这个url，获取最终的url，然后提取bv号
        elif "http" in bvORav:
            url_pattern = r'https?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'  # 匹配url
            urls = re.findall(url_pattern, bvORav)
            if urls:
                bvORav = urls[0]
            else:
                print("[__transform_bv]用户输入的URL不合法")
                self.Label_download_video_tip.setText(f"无法获取URL，请检查后重新输入")
                return False
            r = requests.get(bvORav, headers={"User-Agent": useragent().pcChrome})
            if r.status_code == 200:
                url = r.url
                bv = re.findall(r"BV[0-9a-zA-Z]{10}", url)
                if bv:
                    print(url)
                    print(bv[0])
                    return bv[0]
                else:
                    self.Label_download_video_tip.setText(f"获取BV号失败，请检查URL是否正确")
                    return False
            else:
                print("[__transform_bv]用户输入的URL不合法")
                self.Label_download_video_tip.setText(f"输入的URL不合法，请检查后重新输入")
                return False
        else:
            print("[__transform_bv]用户输入的内容不合法")
            self.Label_download_video_tip.setText(f"暂不支持此种输入，只能输入bv,av,url")
            return False

    # 转换收藏夹输入框的内容为fid号
    def __transform_fav(self, fidORurl):
        """
        输入fid, url，返回得到的fid号或False。
        返回的fid号不一定是准确的，需要self.__check_fav
        False代表转化过程中已经存在问题
        """
        # 如果含有http，尝试访问这个url，获取最终的url，然后提取fid号
        if "http" in fidORurl:
            url_pattern = r'https?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
            urls = re.findall(url_pattern, fidORurl)
            if urls:
                fidORurl = urls[0]
            else:
                print("[__transform_fav]用户输入的URL不合法")
                self.Label_download_fav_tip.setText(f"无法获取URL，请检查后重新输入")
                return False
            r = requests.get(fidORurl, headers={"User-Agent": useragent().pcChrome})
            if r.status_code == 200:
                url = r.url
                fid = re.findall(r"fid=\d+", url)
                if fid:
                    print(url)
                    print(fid[0][4:])
                    return fid[0][4:]
                else:
                    self.Label_download_fav_tip.setText(f"获取FID号失败，请检查URL是否正确")
                    return False
            else:
                print("[__transform_fav]输入不合法")
                self.Label_download_fav_tip.setText(f"url输入不合法，请检查后重新输入")
                return False
        # 如果是数字，直接返回
        elif fidORurl.isdigit():
            return fidORurl
        else:
            print("[__transform_fav]用户输入的内容不合法")
            self.Label_download_fav_tip.setText(f"暂不支持此种输入，只能输入fid,url")
            return False

    # 检查bv号是否合法
    def __check_bv(self, bv_number):
        """检查bv号是否合法"""
        if bv_number is None:
            print("用户未输入BV号")
            self.Label_download_video_tip.setText(f"不输入BV号那下载个锤子啊！")
            return False
        elif bv_number == False:
            print("用户输入的AV号不合法")
            # 对应的self.Label_download_video_tip的变动已经在__transform_bv中实现了
            return False
        # 不是12位的字符串或者不是BV,bv开头就不合法
        elif not (isinstance(bv_number, str) and len(bv_number) == 12 and (bv_number.startswith("BV") or bv_number.startswith("bv"))):
            print("用户输入的BV号不合法")
            self.Label_download_video_tip.setText(f"输入的BV号不合法，请检查后重新输入")
            return False
        else:
            print("用户输入的BV号为：", bv_number)
            return True

    # 检查收藏夹FID是否合法
    def __check_fav(self, fid):
        """检查收藏夹FID是否合法"""
        if not fid:
            print("[__check_fav]用户未输入收藏夹FID")
            self.Label_download_fav_tip.setText(f"不输入收藏夹FID那下载个锤子啊！")
            return False
        # 不是数字就不合法
        elif not (isinstance(fid, str) and fid.isdigit()):
            print("[__check_fav]用户输入的收藏夹FID不合法")
            self.Label_download_fav_tip.setText(f"输入的收藏夹FID不合法，请检查后重新输入")
            return False
        else:
            print("[__check_fav]用户输入的收藏夹FID为：", fid)
            return True

    # 判断视频是否已经存在
    def __check_video_exist(self, bv):
        """
        判断视频是否已经存在
        :param bv: bv号
        :return: True or False
        """
        # 检查save_path里的视频中是否含有有bv的视频
        save_path = UI_Config.config["download_ui"]["video"]["save_path"]
        if not os.path.exists(save_path):
            return False
        for file in os.listdir(save_path):
            if not file.endswith(".mp4"):
                continue
            if bv in file:
                return True
        return False

    # 判断音频是否已经存在
    def __check_audio_exist(self, bv):
        """
        判断音频是否已经存在
        :param bv: bv号
        :return: True or False
        """
        # 检查audio_path里的视频中是否含有有bv的视频
        audio_path = UI_Config.config["download_ui"]["video"]["audio_path"]
        if not os.path.exists(audio_path):
            return False
        for file in os.listdir(audio_path):
            if not file.endswith(".mp3"):
                continue
            if bv in file:
                return True
        return False

    # 获取文件夹的显示文本
    def __shorten_folder_path(self, folder, max_length=50):
        """
        获取文件夹的显示文本
        :param folder: 文件夹路径
        :param max_length: 最大长度
        :return: 显示文本
        """
        folders = folder.split(os.path.sep)  # 使用操作系统的路径分隔符进行分割
        if len(folder) > max_length:
            total_chars = 0
            # 从后往前遍历，直到总字符数超过max_length
            i = len(folders) - 1
            for i in range(len(folders) - 1, -1, -1):
                total_chars += len(folders[i])
                if total_chars > max_length:
                    break
            folder_show = os.path.sep.join(folders[i:])
            folder_show = "...\\" + folder_show
        else:
            folder_show = folder
        return folder_show


