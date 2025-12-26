# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for KakaoTalk AdBlocker Pro v6.0
Build: pyinstaller kakaotalk_adblock.spec
"""

# 경량화를 위한 제외 모듈
EXCLUDES = [
    'matplotlib', 'numpy', 'scipy', 'pandas',
    'cv2', 'torch', 'tensorflow', 'keras', 'sklearn',
    'IPython', 'jupyter', 'notebook', 'pytest',
    'unittest', 'doctest', 'pdb', 'profile', 'pstats',
    'xml.etree', 'xmlrpc', 'email', 'html.parser',
    'distutils', 'setuptools', 'pkg_resources',
]

block_cipher = None

a = Analysis(
    ['카카오톡 광고제거 v6.0.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('blocked_domains.txt', '.'),
    ],
    hiddenimports=[
        'pystray._win32',
        'PIL._tkinter_finder',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
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
    a.zipfiles,
    a.datas,
    [],
    name='KakaoTalkAdBlocker_v6',
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
    uac_admin=True,
    icon=None,  # 아이콘: 'icon.ico'
)
