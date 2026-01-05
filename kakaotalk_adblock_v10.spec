# -*- mode: python ; coding: utf-8 -*-
"""
KakaoTalk AdBlocker Pro v10.0 - PyInstaller Spec File
Optimized for minimal size and fast startup
"""

import sys
from PyInstaller.utils.hooks import collect_submodules

# Minimal data files - only what's needed
datas = []

# Exclude unnecessary modules for smaller build
excludes = [
    # Test frameworks
    'pytest', 'unittest', 'nose',
    # Development tools
    'IPython', 'jupyter', 'notebook',
    # Unused Qt modules
    'PyQt6.QtNetwork', 'PyQt6.QtSql', 'PyQt6.QtMultimedia',
    'PyQt6.QtWebEngine', 'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets',
    'PyQt6.QtQuick', 'PyQt6.QtQml', 'PyQt6.QtDesigner',
    'PyQt6.Qt3DCore', 'PyQt6.Qt3DRender', 'PyQt6.Qt3DInput',
    'PyQt6.QtBluetooth', 'PyQt6.QtNfc', 'PyQt6.QtPositioning',
    'PyQt6.QtSensors', 'PyQt6.QtSerialPort', 'PyQt6.QtHelp',
    'PyQt6.QtPdf', 'PyQt6.QtSvg', 'PyQt6.QtOpenGL',
    # Unused standard library
    'tkinter', 'turtle', 'turtledemo',
    'lib2to3', 'pydoc', 'doctest',
    'xmlrpc', 'ftplib', 'imaplib', 'poplib', 'smtplib', 'nntplib',
    'telnetlib', 'mailbox', 'email.mime',
    # Scientific libs (if accidentally included)
    'numpy', 'scipy', 'pandas', 'matplotlib',
    # Other unused
    'PIL', 'cv2', 'cryptography', 'ssl',
]

# Hidden imports that might be needed
hiddenimports = [
    'ad_sniffer',
]

a = Analysis(
    ['카카오톡 광고제거 v10.0.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=2,  # Python optimization level
)

# Remove unnecessary binaries/data for size reduction
def filter_binaries(binaries):
    """Filter out large/unnecessary binaries"""
    exclude_patterns = [
        'Qt6WebEngine', 'Qt6Quick', 'Qt6Qml', 'Qt6Designer',
        'Qt6Pdf', 'Qt63D', 'Qt6Bluetooth', 'Qt6Nfc',
        'Qt6Multimedia', 'Qt6Network', 'Qt6Sql',
        'opengl32sw', 'd3dcompiler',
        'libcrypto', 'libssl',
    ]
    filtered = []
    for name, path, type in binaries:
        if not any(pattern in name for pattern in exclude_patterns):
            filtered.append((name, path, type))
    return filtered

a.binaries = filter_binaries(a.binaries)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='KakaoTalk_AdBlocker_v10',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,  # Windows doesn't support strip
    upx=True,  # Use UPX compression if available
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one
    version=None,
    uac_admin=False,  # Request admin at runtime, not at launch
)
