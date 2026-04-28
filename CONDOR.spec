# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

# Detectar archivos
icon_file = 'condor.ico' if os.path.exists('condor.ico') else None
prompt_file = 'prompt.txt' if os.path.exists('prompt.txt') else None

datas = []
if icon_file:
    datas.append((icon_file, '.'))
if prompt_file:
    datas.append((prompt_file, '.'))

# Detectar tkinterdnd2
try:
    import tkinterdnd2
    dnd_path = os.path.dirname(tkinterdnd2.__file__)
    datas.append((dnd_path, 'tkinterdnd2'))
except ImportError:
    pass

a = Analysis(
    ['condor.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'tkinterdnd2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CONDOR',
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
    icon=icon_file,
)