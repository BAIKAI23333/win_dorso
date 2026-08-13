# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for WinDorso.

onedir mode (not onefile): fast startup and fewer antivirus false positives.

Key pieces:
- collect_all('mediapipe'): pose models (.tflite) are package data and the
  solutions submodules are imported lazily — static analysis alone misses both
- collect_data_files('PyQt6', 'Qt6/translations'): QLibraryInfo.path()
  resolves TranslationsPath inside the bundle; without this, main.py's
  qt_zh_CN translator load fails silently and standard dialogs show English
"""

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# mediapipe needs collect_* because the pose models (.tflite) are package data
# and the solutions submodules are imported lazily. genai/* (jax-based LLM
# tooling) and *_test modules are never touched by mp.solutions.pose — dropping
# them keeps jax/jaxlib/scipy/sounddevice (~280 MB) out of the bundle.
_keep_module = lambda name: (
    "genai" not in name and ".test" not in name and not name.endswith("_test")
)
hiddenimports = collect_submodules("mediapipe", filter=_keep_module)
datas = collect_data_files("mediapipe")
binaries = collect_dynamic_libs("mediapipe")
datas += collect_data_files("PyQt6", subdir="Qt6/translations")
# main.py loads it via _resource_path() for the window/taskbar icon
datas.append(("assets/win_dorso.ico", "assets"))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "jax",
        "jaxlib",
        "opt_einsum",
        "ml_dtypes",
        "scipy",
        "sounddevice",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WinDorso",
    icon="assets/win_dorso.ico",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX often breaks Qt/OpenCV binaries and trips antivirus
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WinDorso",
)
