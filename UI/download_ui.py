import os
import time
import random
from functools import partial

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit
from PyQt6.QtCore import QThread, pyqtSignal

from Tools.bili_tools import biliVideo, biliFav
from UI.config import Button_css
Button_css = Button_css()

class DownloadThread(QThread):
    # 定义一个信号，用于在下载完成时发射：bool下载是否成功，str提示语类型，tuple当前下载的进度， strBV号
    download_finished = pyqtSignal(bool, str, tuple, str)

    def __init__(self, bv_number, down_type, tip_type, current_process=(1, 1), parent=None):
        super().__init__(parent)
        self.bv_number = bv_number  # 视频BV号
        self.down_type = down_type  # 下载类型(视频va、音频audio)
        self.tip_type = tip_type  # 提示语类型(视频video、收藏夹fav)
        self.current_process = current_process  # 当前下载的进度，默认是(1, 1)，其余时候是(i, N), i=1~N

    def run(self):
        print(f"开始下载{self.down_type}，BV号：{self.bv_number}")
        biliV = biliVideo(self.bv_number)
        success = False
        if self.down_type == 'va':
            success = biliV.download_video_with_audio(save_video_path='output', save_audio_path='output', save_path='output')
        elif self.down_type == 'audio':
            success = biliV.download_audio(save_audio_path='output')
        print(f"下载结果：{success}")
        self.download_finished.emit(success, self.tip_type, self.current_process, self.bv_number)  # 发射信号


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

        # 创建视频下载的输入框&按钮的水平布局
        HLayout_video = self._init_HLayout_video()
        # 创建提示文本
        self.Label_download_video_tip = QLabel("输入BV号后，点击下载按钮开始下载")
        # 创建收藏夹下载的输入框&按钮的水平布局
        HL_fav = self._init_HLayout_fav()
        # 创建提示文本
        self.Label_download_fav_tip = QLabel("输入收藏夹fid后，点击下载按钮开始下载")

        V_Layout_main.addLayout(HLayout_video)
        V_Layout_main.addWidget(self.Label_download_video_tip)
        V_Layout_main.addLayout(HL_fav)
        V_Layout_main.addWidget(self.Label_download_fav_tip)
        V_Layout_main.addStretch(1)
        return V_Layout_main

    def _init_HLayout_video(self):
        HLayout_video = QHBoxLayout()

        # 创建提示文本
        Label_bv_prompt = QLabel("BV号：")
        # 创建输入框
        self.Line_bv_input = QLineEdit()
        # 创建下载按钮
        btns_download = self.__init_Widget_btn_video()

        HLayout_video.addWidget(Label_bv_prompt)
        HLayout_video.addWidget(self.Line_bv_input)
        HLayout_video.addStretch(1)
        HLayout_video.addWidget(btns_download)
        HLayout_video.addStretch(10)
        return HLayout_video

    def _init_HLayout_fav(self):
        HL_fav = QHBoxLayout()
        # 创建提示文本
        Label_fav_prompt = QLabel("收藏夹FID：")
        # 创建输入框
        self.Line_fav_input = QLineEdit()
        # 创建下载按钮
        btns_download = self.__init_Widget_btn_fav()

        HL_fav.addWidget(Label_fav_prompt)
        HL_fav.addWidget(self.Line_fav_input)
        HL_fav.addStretch(1)
        HL_fav.addWidget(btns_download)
        HL_fav.addStretch(10)
        return HL_fav

    def __init_Widget_btn_video(self):
        btn_widget = QWidget()
        HLayout_btn = QHBoxLayout()
        # 创建下载按钮
        btn_download = QPushButton("下载")
        btn_download.setStyleSheet(Button_css.BTN_BLUE_PURPLE)
        btn_download.clicked.connect(partial(self.__on_download_clicked, down_type='va'))
        # 创建下载音频按钮
        btn_download_audio = QPushButton("下载音频")
        btn_download_audio.setStyleSheet(Button_css.BTN_BLUE_PURPLE)
        btn_download_audio.clicked.connect(partial(self.__on_download_clicked, down_type='audio'))
        HLayout_btn.addWidget(btn_download)
        HLayout_btn.addWidget(btn_download_audio)
        btn_widget.setLayout(HLayout_btn)
        return btn_widget

    def __init_Widget_btn_fav(self):
        btn_widget = QWidget()
        HLayout_btn = QHBoxLayout()
        # 创建下载视频按钮
        btn_download = QPushButton("下载")
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

    def __on_download_clicked(self, down_type):
        # 获取用户输入的内容
        bv_number = self.Line_bv_input.text()
        self.bv = bv_number
        self.down_type = down_type
        if not self.bv:
            print("用户未输入BV号")
            self.Label_download_video_tip.setText(f"不输入BV号那下载个锤子啊！")
        # 不是12位的字符串或者不是BV,bv开头就不合法
        elif not (isinstance(self.bv, str) and len(self.bv) == 12 and (self.bv.startswith("BV") or self.bv.startswith("bv"))):
            print("用户输入的BV号不合法")
            self.Label_download_video_tip.setText(f"输入的BV号不合法，请检查后重新输入")
        else:
            print("用户输入的BV号为：", self.bv)
            self.Label_download_video_tip.setText(f"正在下载{self.bv}")
            if down_type == 'va' and os.path.exists(f"output/{self.bv}视频.mp4"):
                print("视频已经存在，不再下载")
                self.Label_download_video_tip.setText(f"视频{self.bv}已经存在，不需要再次下载")
            elif down_type == 'audio' and os.path.exists(f"output/{self.bv}音频.mp3"):
                print("音频已经存在，不再下载")
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

    def __on_download_fav_clicked(self, down_type):
        fid = self.Line_fav_input.text()

        self.fid = fid  # 收藏夹fid
        self.down_type = down_type  # 下载类型：视频va/音频audio
        bv_count = 0  # 需要下载的视频数量（也就是去掉已经下载的视频）

        if not self.fid:
            print("用户未输入收藏夹FID")
            self.Label_download_fav_tip.setText(f"不输入收藏夹FID那下载个锤子啊！")
        # 不是数字就不合法
        elif not (isinstance(self.fid, str) and self.fid.isdigit()):
            print("用户输入的收藏夹FID不合法")
            self.Label_download_fav_tip.setText(f"输入的收藏夹FID不合法，请检查后重新输入")
        else:
            print("用户输入的收藏夹FID为：", self.fid)  # 如2525700378
            self.Label_download_fav_tip.setText(f"正在获取收藏夹{self.fid}的视频BV号，别急")
            biliF = biliFav()
            bvids = biliF.get_fav_bv(self.fid)
            print(bvids)
            self.Label_download_fav_tip.setText(f"正在准备下载，共有{len(bvids)}个视频需要下载")
            self.download_thread = []
            for i, bvid in enumerate(bvids):
                if down_type == 'va' and os.path.exists(f"output/{bvid}视频.mp4"):
                    print(f"视频{bvid}已经存在，不再下载")
                    self.Label_download_fav_tip.setText(f"视频{bvid}已经存在，不需要再次下载")
                elif down_type == 'audio' and os.path.exists(f"output/{bvid}音频.mp3"):
                    print(f"音频{bvid}已经存在，不再下载")
                    self.Label_download_fav_tip.setText(f"音频{bvid}已经存在，不需要再次下载")
                else:
                    bv_count += 1
                    # todo: 这里的进度条有问题，因为len(bvids)是不准确的，应该看最终需要下载的数量，所以应该先全部检查一遍再开始下载
                    self.download_thread_i = DownloadThread(bvid, down_type, 'fav', (i + 1, len(bvids)))
                    self.download_thread_i.download_finished.connect(self.__on_download_finished)
                    self.download_thread.append(self.download_thread_i)
                    time.sleep(random.uniform(0.5, 1))  # 防止请求过快导致封号
            if bv_count == 0:
                self.Label_download_fav_tip.setText(f"收藏夹{self.fid}的视频已经全部存在，不需要再次下载")
            else:
                for thread in self.download_thread:
                    thread.start()
                self.Label_download_fav_tip.setText(f"进程已经全部开始，共有{bv_count}个视频需要下载")

    def __on_download_finished(self, success, tip_type, current_process, bv_number):
        if not success:
            print("下载失败")
            if tip_type == 'video':
                self.Label_download_video_tip.setText(f"当前进度：{current_process[0]}/{current_process[1]}。"
                                                      f"视频{bv_number}下载失败，一般是因为视频失效了，小概率是其他原因")
            elif tip_type == 'fav':
                self.Label_download_fav_tip.setText(f"当前进度：{current_process[0]}/{current_process[1]}。"
                                                    f"收藏夹视频{bv_number}下载失败，一般是因为视频失效了，小概率是其他原因")
            else:
                self.Label_download_video_tip.setText(f"当前进度：{current_process[0]}/{current_process[1]}。"
                                                      f"[代码进入错误路径]请注意tip_type的值，当前视频{bv_number}下载失败")
        else:
            print("下载完成")
            if tip_type == 'video':
                if current_process == (1, 1):
                    self.Label_download_video_tip.setText(f"视频{bv_number}已经下载完毕。"
                                                          "提示：下载的视频和音频将保存在output文件夹中（目前默认就这样，我现在懒得优化）")
                else:
                    self.Label_download_video_tip.setText(f"当前进度：{current_process[0]}/{current_process[1]}，视频{bv_number}。"
                                                          "提示：下载的视频和音频将保存在output文件夹中（目前默认就这样，我现在懒得优化）")
            elif tip_type == 'fav':
                if current_process == (1, 1):
                    self.Label_download_fav_tip.setText(f"收藏夹视频{bv_number}已经下载完毕。"
                                                        "提示：下载的视频和音频将保存在output文件夹中（目前默认就这样，我现在懒得优化）")
                else:
                    self.Label_download_fav_tip.setText(f"当前进度：{current_process[0]}/{current_process[1]}，收藏夹视频{bv_number}。"
                                                        "提示：下载的视频和音频将保存在output文件夹中（目前默认就这样，我现在懒得优化）")
            else:
                self.Label_download_video_tip.setText(f"[代码进入错误路径]请注意tip_type的值，当前视频{bv_number}下载成功")
