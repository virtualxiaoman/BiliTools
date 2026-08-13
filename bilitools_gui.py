"""BiliTools 桌面版启动入口（PyInstaller 打包 / 双击运行）。

    python bilitools_gui.py
"""
import sys

from frontend.pyside6.app import main

if __name__ == "__main__":
    sys.exit(main())
