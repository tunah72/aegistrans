# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the desktop app (Windows & macOS).

One-folder / macOS app bundle, deliberately not --onefile: onnxruntime, opencv, and PyMuPDF push
the bundle past 400 MB, and onefile re-extracts all of that to a temp directory
on every launch, which is slow and trips antivirus heuristics.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH)

# Read APP_VERSION if available
app_version = "0.2.0"
update_file = ROOT / "app" / "update.py"
if update_file.is_file():
    for line in update_file.read_text(encoding="utf-8").splitlines():
        if line.startswith('APP_VERSION = "'):
            app_version = line.split('"')[1]
            break

datas = []
for optional in ("app/fonts", "app/assets"):
    directory = ROOT / optional
    if not directory.is_dir():
        continue
    for item in sorted(directory.iterdir()):
        # onnxruntime caches a hardware-specific optimised graph next to the
        # model. It is 75 MB, and it is only valid on the machine that built it.
        if item.is_file() and item.suffix != ".optimized":
            datas.append((str(item), optional))

datas += collect_data_files("customtkinter")
datas += collect_data_files("tkinterdnd2")
datas += collect_data_files("babeldoc")

hiddenimports = [
    "peewee",
    "pdf2zh.doclayout",  # reached through importlib.import_module, not a static import
    "pdf2zh.high_level",
    "pdf2zh.converter",
    "pdf2zh.translator",
]

analysis = Analysis(
    [str(ROOT / "app" / "gui.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "IPython",
        "pytest",
        "scipy",
        "pandas",
        # Model-optimisation trees pulled in with onnxruntime. Inference never
        # touches them, and they drag in torch and transformers references.
        "onnxruntime.transformers",
        "onnxruntime.tools",
        "onnxruntime.quantization",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

icon_file = "icon.icns" if sys.platform == "darwin" else "icon.ico"
icon_path = ROOT / "app" / "assets" / icon_file
icon_str = str(icon_path) if icon_path.is_file() else None

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="AegisTrans",
    icon=icon_str,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AegisTrans",
)

if sys.platform == "darwin":
    app = BUNDLE(
        collect,
        name="AegisTrans.app",
        icon=icon_str,
        bundle_identifier="com.tunah72.aegistrans",
        info_plist={
            "CFBundleDisplayName": "AegisTrans",
            "CFBundleName": "AegisTrans",
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": app_version,
            "CFBundleVersion": app_version,
            "NSHighResolutionCapable": True,
            "LSBackgroundOnly": False,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
