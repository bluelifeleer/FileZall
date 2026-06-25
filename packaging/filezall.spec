# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


block_cipher = None
icon_dir = "../src/filezall_desktop/assets/icons"

# Entry module: filezall_desktop.app

a = Analysis(
    ["../src/filezall_desktop/app.py"],
    pathex=["..", "../src"],
    binaries=[],
    datas=[(icon_dir, "filezall_desktop/assets/icons")],
    hiddenimports=collect_submodules("filezall_core") + collect_submodules("filezall_desktop"),
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
    [],
    exclude_binaries=True,
    name="FileZall",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=f"{icon_dir}/filezall.ico",
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="FileZall",
)

app = BUNDLE(
    coll,
    name="FileZall.app",
    icon=f"{icon_dir}/filezall.icns",
    bundle_identifier="com.filezall.desktop",
)
