# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

from PyInstaller.utils.hooks import collect_submodules

# 불필요한 라이브러리 제외 (경량화)
excluded_modules = [
    'matplotlib', 'scipy', 'pandas', 'numpy', 
    'tkinter.test', 'unittest', 'email', 'http', 'xml', 'pydoc'
]

hiddenimports = ['psutil', 'PIL', 'pystray']
hiddenimports += collect_submodules('pywinauto')
hiddenimports += collect_submodules('comtypes')
try:
    hiddenimports += collect_submodules('win32com')
except Exception:
    pass

a = Analysis(
    ['카카오톡 광고제거 v10.0.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('blocked_domains.txt', '.'),
        ('adblock_settings.json', '.'),
        ('ad_patterns.json', '.')
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
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
    name='KakaoTalkAdBlocker_Pro_v10.0', # 출력 파일명
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True, # UPX 압축 사용 (있으면 경량화됨)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # 콘솔창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,  # 관리자 권한 요청 필수
)
