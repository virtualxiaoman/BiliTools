# -*- mode: python ; coding: utf-8 -*-
# BiliTools 桌面版打包配置（PyInstaller，单文件，无控制台窗口）
# 构建：在项目根目录执行  venv/Scripts/pyinstaller bilitools.spec --noconfirm

a = Analysis(
    ['bilitools_gui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BiliTools',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/imgs/ico/arona.ico'],
)
