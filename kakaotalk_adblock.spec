# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

PROJECT_ROOT = Path(__file__).resolve().parent

hiddenimports = ["psutil", "PIL", "pystray"]
hiddenimports += collect_submodules("pystray")

a = Analysis(
    [str(PROJECT_ROOT / "kakaotalk_layout_adblock_v11.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        (str(PROJECT_ROOT / "layout_settings_v11.json"), "."),
        (str(PROJECT_ROOT / "layout_rules_v11.json"), "."),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "unittest", "pywinauto", "comtypes"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="KakaoTalkLayoutAdBlocker_v11",
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
