# CONDOR.spec
block_cipher = None

a = Analysis(
    ['condor.py'],
    pathex=[],
    binaries=[],
    datas=[('condor.ico', '.')],
    hiddenimports=[
        'pystray',
        'PIL',
        'PIL.Image',
        'PIL._imagingtk',
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
    icon='condor.ico',
)