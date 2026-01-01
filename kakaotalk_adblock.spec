# -*- mode: python ; coding: utf-8 -*-
"""
카카오톡 광고 차단기 Pro v4.0 - PyInstaller Spec File
======================================================
빌드 명령: pyinstaller kakaotalk_adblock.spec
출력 위치: dist/카카오톡 광고차단기 v4.0.exe
"""

import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# 숨겨진 임포트 수집
hidden_imports = [
    'psutil',
    'pystray',
    'pystray._win32',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'PIL._tkinter_finder',
    'queue',
    'threading',
    'ctypes',
    'ctypes.wintypes',
    'json',
    'logging',
    'dataclasses',
]

# PIL 서브모듈 자동 수집
hidden_imports += collect_submodules('PIL')

a = Analysis(
    ['카카오톡 광고제거 v4.0.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 불필요한 모듈 제외 (파일 크기 최적화)
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'cv2',
        'tensorflow',
        'torch',
        'sklearn',
        'notebook',
        'jupyter',
        'IPython',
        'test',
        'tests',
        'unittest',
        'pytest',
        'doctest',
        '_pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 중복 바이너리 제거
a.binaries = list(set(a.binaries))

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='카카오톡 광고차단기 v4.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI 앱이므로 콘솔 창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,  # 관리자 권한 요청 (중요!)
    icon=None,  # 아이콘 파일 경로 (예: 'icon.ico')
    version_info=None,  # 버전 정보 파일 (예: 'version.txt')
)

# 빌드 후 정보 출력
print("\n" + "=" * 60)
print("빌드 완료!")
print("=" * 60)
print(f"출력 파일: dist/카카오톡 광고차단기 v4.0.exe")
print("=" * 60)
