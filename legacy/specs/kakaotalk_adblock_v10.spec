# -*- mode: python ; coding: utf-8 -*-
"""
Legacy filename kept for build-script compatibility.
Build target is v11 layout-only entrypoint.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

_SPEC_PATH = Path(globals().get("__file__", "legacy/specs/kakaotalk_adblock_v10.spec")).resolve()
PROJECT_ROOT = _SPEC_PATH.parents[2]

hiddenimports = [
    "psutil",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "pystray",
    "kakao_adblocker",
    "kakao_adblocker.app",
    "kakao_adblocker.config",
    "kakao_adblocker.event_engine",
    "kakao_adblocker.layout_engine",
    "kakao_adblocker.logging_setup",
    "kakao_adblocker.protocols",
    "kakao_adblocker.services",
    "kakao_adblocker.ui",
    "kakao_adblocker.win32_api",
]
hiddenimports += collect_submodules("pystray")
hiddenimports += collect_submodules("PIL")

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
