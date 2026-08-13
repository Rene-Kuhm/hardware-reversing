# -*- mode: python ; coding: utf-8 -*-
import os

# SPECPATH is injected by PyInstaller and points at this file's directory
# (hydrotemp-aio/macos/build), so the source resolves in any clone.
SRC = os.path.normpath(os.path.join(SPECPATH, '..', 'monitor_macos.py'))

a = Analysis(
    [SRC],
    pathex=[],
    binaries=[
        ('/usr/local/opt/hidapi/lib/libhidapi.0.15.0.dylib', '.'),
        ('/usr/local/opt/hidapi/lib/libhidapi.dylib', '.'),
    ],
    datas=[],
    hiddenimports=['hid', 'psutil', 'ctypes', 'ctypes.util'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'email', 'html', 'http', 'xml', 'pydoc'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='aio-display',
    debug=False,
    strip=True,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=False,
    name='aio-display',
)
