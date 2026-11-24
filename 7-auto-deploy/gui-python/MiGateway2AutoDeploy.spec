# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
assets = Path(os.environ["MI_GW2_BUILD_ASSETS"])
icon = root / "icon.png"

a = Analysis(
    ["app.py"],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(assets), "assets"),
        (str(icon), "."),
        (str(root / "VERSION"), "."),
    ] + collect_data_files("customtkinter"),
    hiddenimports=[
        "PIL._tkinter_finder",
        "customtkinter",
        "darkdetect",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MiGateway2AutoDeploy",
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
    icon=[str(root / "app.ico")],
    version=os.environ["MI_GW2_BUILD_VERSION_INFO"],
    uac_admin=os.environ.get("MI_GW2_NO_UAC") != "1",
)
