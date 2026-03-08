# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['makingprogram.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\ding9\\AppData\\Local\\Python\\pythoncore-3.14-64\\Lib\\site-packages\\customtkinter', 'customtkinter/')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'scipy', 'matplotlib', 'IPython', 'zmq', 'jedi', 'notebook', 'PyQt5', 'PyQt6', 'PySide6'],
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
    name='makingprogram',
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
)
