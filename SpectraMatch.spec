# -*- mode: python ; coding: utf-8 -*-
import os
import sys

block_cipher = None
project_root = os.path.abspath('.')

# 1. データの定義（アイコン等のみ。torch/transformersは除外）
datas = [
    (os.path.join(project_root, 'icon'), 'icon'),
]

# 2. 隠しインポート（GUIや基本機能のみ）
hiddenimports = [
    'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
    'cv2', 'numpy', 'PIL', 'PIL.Image', 'send2trash',
    'core', 'core.scanner', 'core.clip_engine', 'core.database', 
    'core.comparator', 'core.hasher', 'core.faiss_engine',
    'gui', 'gui.main_window', 'gui.image_grid', 'gui.styles'
]

# 3. 除外モジュール（ここで AIライブラリを明示的に除外）
excludes = [
    'torch', 'transformers', 'tokenizers', 'huggingface_hub', 
    'safetensors', 'intel_openmp', 'matplotlib', 'tkinter'
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SpectraMatch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon\\icon.png'] if os.path.exists('icon\\icon.png') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SpectraMatch',
)
