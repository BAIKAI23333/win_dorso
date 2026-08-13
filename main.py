"""WinDorso – Windows posture monitor that blurs the screen when you slouch.

Inspired by tldev/dorso (macOS). Uses MediaPipe Pose + PyQt6.
"""

import ctypes
import os
import sys
from ctypes import wintypes

from PyQt6.QtCore import QLibraryInfo, QTranslator
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from main_window import MainWindow


def _resource_path(name: str) -> str:
    """Locate a bundled asset in both dev and PyInstaller-frozen modes."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

# Keep the mutex handle alive for the whole process lifetime
_mutex_handle = None

_kernel32 = ctypes.windll.kernel32
_kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE


def _ensure_single_instance() -> bool:
    """Prevent two instances fighting over the camera and the hotkey."""
    global _mutex_handle
    _mutex_handle = _kernel32.CreateMutexW(None, False, "WinDorso_SingleInstance_Mutex")
    return _kernel32.GetLastError() != 183  # 183 = ERROR_ALREADY_EXISTS


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    # Base font: 11pt rows per the dorso design language
    font = QFont()
    font.setFamily("Microsoft YaHei UI")
    font.setPointSize(11)
    app.setFont(font)

    # Window/taskbar icon — set explicitly so it does not rely on the
    # exe's embedded icon (which Explorer caches aggressively)
    app.setWindowIcon(QIcon(_resource_path(os.path.join("assets", "win_dorso.ico"))))

    # Load Qt's built-in Chinese translation for standard dialogs
    translator = QTranslator(app)
    if translator.load("qt_zh_CN", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)

    if not _ensure_single_instance():
        from config import AppConfig
        from i18n import translate
        lang = AppConfig().language
        QMessageBox.warning(
            None, "WinDorso", translate("程序已在运行中，请勿重复启动", lang)
        )
        sys.exit(0)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
