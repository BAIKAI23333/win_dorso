"""Main window — Dorso-style single scrollable settings page.

Design language follows the dorso-design skill: brandCyan #4fd1c5 accents,
subtle opacity-based neutrals, 11pt rows / 12pt card titles, SettingsCard
containers, BrandSwitch toggles, segmented style picker, value capsules.

Supports dark/light themes, zh/en languages, fullscreen (F11) and a
resizable, responsive layout (size is persisted).
"""

import ctypes
import sys
import threading
import time
from ctypes import wintypes

import cv2
import numpy as np
from PyQt6.QtCore import (
    QAbstractNativeEventFilter, QEasingCurve, QEvent, QObject, QRectF, QSize,
    Qt, QTimer, QVariantAnimation, pyqtSignal, pyqtSlot,
)
from PyQt6.QtGui import (
    QColor, QGuiApplication, QImage, QKeySequence, QPainter, QPixmap, QShortcut,
)
from PyQt6.QtWidgets import (
    QAbstractButton, QApplication, QColorDialog, QComboBox, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QToolButton, QVBoxLayout,
    QWidget,
)

from config import AppConfig, STYLE_LABELS
from posture_detector import PostureDetector, camera_lock
from blur_overlay import BlurOverlay
from i18n import translate

STYLE_ORDER = list(STYLE_LABELS.keys())

NAMED_COLORS = [
    ("黑色", "#000000"),
    ("白色", "#FFFFFF"),
    ("红色", "#C82020"),
    ("橙色", "#FF8C00"),
    ("黄色", "#FFD700"),
    ("绿色", "#2E8B57"),
    ("蓝色", "#1E90FF"),
    ("紫色", "#8A2BE2"),
]

POSITIONS = [
    ("左上", "tl"), ("上中", "tc"), ("右上", "tr"),
    ("左中", "cl"), ("居中", "cc"), ("右中", "cr"),
    ("左下", "bl"), ("下中", "bc"), ("右下", "br"),
]

BRAND_CYAN = "#4fd1c5"
ON_CYAN = "#1a2744"

# ---- theme tokens (dark / light) ----

THEME_TOKENS = {
    "dark": {
        "bg": "#262626", "card": "#2e2e2e",
        "text": "#d9d9d9", "text_secondary": "#9a9a9a",
        "border": "rgba(255,255,255,0.06)",
        "input_bg": "#333333", "input_border": "rgba(255,255,255,0.08)",
        "btn_bg": "#3d3d3d", "btn_border": "#555555", "btn_hover": "#4a4a4a",
        "btn_text": "#dddddd",
        "slider_track": "rgba(255,255,255,0.08)",
        "seg_fill": "rgba(255,255,255,0.06)",
        "seg_btn_text": "#c8c8c8", "seg_hover": "rgba(255,255,255,0.05)",
        "chip_fill": "rgba(255,255,255,0.06)", "chip_border": "rgba(255,255,255,0.1)",
        "chip_text": "#e0e0e0",
        "scroll_handle": "rgba(255,255,255,0.15)",
        "scroll_handle_hover": "rgba(255,255,255,0.25)",
        "switch_off": (255, 255, 255, 38), "switch_text": (0xDD, 0xDD, 0xDD),
        "preview_bg": "#111111",
    },
    "light": {
        "bg": "#f5f5f5", "card": "#ffffff",
        "text": "#333333", "text_secondary": "#777777",
        "border": "rgba(0,0,0,0.06)",
        "input_bg": "#ffffff", "input_border": "rgba(0,0,0,0.1)",
        "btn_bg": "#ffffff", "btn_border": "#cccccc", "btn_hover": "#e8e8e8",
        "btn_text": "#333333",
        "slider_track": "rgba(0,0,0,0.08)",
        "seg_fill": "rgba(0,0,0,0.06)",
        "seg_btn_text": "#555555", "seg_hover": "rgba(0,0,0,0.05)",
        "chip_fill": "rgba(0,0,0,0.06)", "chip_border": "rgba(0,0,0,0.1)",
        "chip_text": "#333333",
        "scroll_handle": "rgba(0,0,0,0.2)",
        "scroll_handle_hover": "rgba(0,0,0,0.3)",
        "switch_off": (0, 0, 0, 38), "switch_text": (0x33, 0x33, 0x33),
        "preview_bg": "#111111",  # camera viewport stays dark in both themes
    },
}

# ---- anti-misclick controls (wheel never changes a value) ----


class NoWheelComboBox(QComboBox):
    """Combo box that ignores the mouse wheel — scrolling the settings page
    over a combo must never change its selection."""

    def wheelEvent(self, event):
        event.ignore()


class NoWheelSlider(QSlider):
    """Slider that ignores the mouse wheel — same anti-misclick rationale."""

    def wheelEvent(self, event):
        event.ignore()


# ---- Dorso design components ----


class SettingsCard(QWidget):
    """Card matching Dorso SettingsCard: 11pt brandCyan icon + 12pt semibold
    title, radius 10, border primary 0.06, padding 12, content spacing 6.
    Theme colors come from the global stylesheet (objectName selectors)."""

    def __init__(self, icon: str, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 12)
        v.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(6)
        self.icon_lbl = QLabel(icon)
        self.icon_lbl.setObjectName("cardIcon")
        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("cardTitle")
        header.addWidget(self.icon_lbl)
        header.addWidget(self.title_lbl)
        header.addStretch()
        v.addLayout(header)

        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(6)
        v.addLayout(self.content_layout)


class BrandSwitch(QAbstractButton):
    """Dorso BrandSwitch: 30x18 capsule, 14x14 white knob, animated 0.15 s
    easeInOut on toggle; the whole row is clickable. Initial state (set before
    the widget is shown) is applied instantly — no startup animation.
    Theme colors come from class attributes refreshed by _apply_theme."""

    CAPSULE_W, CAPSULE_H = 30, 18
    KNOB = 14

    off_fill = QColor(255, 255, 255, 38)
    text_color = QColor(0xDD, 0xDD, 0xDD)

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(22)
        self._offset = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.InOutQuad))
        self._anim.valueChanged.connect(self._on_anim_value)
        self.toggled.connect(self._on_toggled)

    def _on_anim_value(self, v):
        self._offset = float(v)
        self.update()

    def _on_toggled(self, checked):
        if not self.isVisible():
            # Programmatic initial setChecked — instant state, no animation
            self._offset = 1.0 if checked else 0.0
            self.update()
            return
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(self.CAPSULE_W + 10 + fm.horizontalAdvance(self.text()), 22)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._offset

        # Fill: primary 0.15 (off) -> brandCyan (on), interpolated
        off = self.off_fill
        on = QColor(0x4F, 0xD1, 0xC5, 255)
        fill = QColor(
            int(off.red() + (on.red() - off.red()) * t),
            int(off.green() + (on.green() - off.green()) * t),
            int(off.blue() + (on.blue() - off.blue()) * t),
            int(off.alpha() + (on.alpha() - off.alpha()) * t),
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(0, 2, self.CAPSULE_W, self.CAPSULE_H), 9, 9)

        # White knob, 2pt inset
        knob_x = 2 + t * (self.CAPSULE_W - self.KNOB - 4)
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QRectF(knob_x + 2, 4, self.KNOB, self.KNOB))

        # Row label
        p.setPen(self.text_color)
        p.setFont(self.font())
        p.drawText(
            QRectF(self.CAPSULE_W + 10, 0, self.width() - self.CAPSULE_W - 10, 22),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text(),
        )
        p.end()


class CollapsibleSection(QWidget):
    """Section with a clickable arrow header that truly collapses its content."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.header = QToolButton()
        self.header.setText(title)
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.header.setArrowType(Qt.ArrowType.DownArrow)
        self.header.toggled.connect(self._on_toggled)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(6)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        v.addWidget(self.header)
        v.addWidget(self.content)

    def _on_toggled(self, checked):
        self.header.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )
        self.content.setVisible(checked)


class HotkeyEdit(QLineEdit):
    """Read-only chip showing the current hotkey; click to record a new one."""

    def __init__(self, text: str, on_click):
        super().__init__(text)
        self._on_click = on_click
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mousePressEvent(event)


# ---- global hotkey (default Ctrl+Alt+D, customizable) ----

HOTKEY_ID = 0xD0C0
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

_user32 = ctypes.windll.user32
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.UnregisterHotKey.restype = wintypes.BOOL


def qt_key_to_vk(key: int) -> int:
    if Qt.Key.Key_A.value <= key <= Qt.Key.Key_Z.value:
        return ord(chr(key))
    if Qt.Key.Key_0.value <= key <= Qt.Key.Key_9.value:
        return ord(chr(key))
    if Qt.Key.Key_F1.value <= key <= Qt.Key.Key_F12.value:
        return 0x70 + (key - Qt.Key.Key_F1.value)
    return 0


def qt_mods_to_win(mods) -> int:
    win = 0
    if mods & Qt.KeyboardModifier.ControlModifier:
        win |= MOD_CONTROL
    if mods & Qt.KeyboardModifier.AltModifier:
        win |= MOD_ALT
    if mods & Qt.KeyboardModifier.ShiftModifier:
        win |= MOD_SHIFT
    if mods & Qt.KeyboardModifier.MetaModifier:
        win |= MOD_WIN
    return win


def hotkey_label(mods: int, vk: int) -> str:
    parts = []
    if mods & MOD_CONTROL:
        parts.append("Ctrl")
    if mods & MOD_ALT:
        parts.append("Alt")
    if mods & MOD_SHIFT:
        parts.append("Shift")
    if mods & MOD_WIN:
        parts.append("Win")
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        parts.append(chr(vk))
    elif 0x70 <= vk <= 0x7B:
        parts.append(f"F{vk - 0x6F}")
    else:
        parts.append(f"0x{vk:X}")
    return "+".join(parts)


class HotkeyFilter(QAbstractNativeEventFilter):
    """Catches WM_HOTKEY from the OS and invokes the callback on the GUI thread."""

    def __init__(self, on_hotkey):
        super().__init__()
        self._on_hotkey = on_hotkey

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._on_hotkey()
                return True, 0
        return False, 0


class KeyCaptureFilter(QObject):
    """Captures the next real key press app-wide while hotkey recording is active."""

    MODIFIER_KEYS = {
        Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
    }

    def __init__(self, on_key, on_cancel):
        super().__init__()
        self._on_key = on_key
        self._on_cancel = on_cancel
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_cancel)
        self._timeout.start(10000)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_F11 and event.modifiers() == Qt.KeyboardModifier.NoModifier:
                return False  # let F11 (fullscreen toggle) pass through
            if key in self.MODIFIER_KEYS:
                # Keep waiting for the real key — do NOT stop the timeout,
                # or pressing Ctrl (the first key of any combo) would
                # permanently disable the 10 s auto-cancel
                return True
            self._timeout.stop()
            if key == Qt.Key.Key_Escape:
                self._on_cancel()
            else:
                self._on_key(event.modifiers(), key)
            return True
        return super().eventFilter(obj, event)


class MainWindow(QMainWindow):
    """Scrollable settings window: resizable, theme/language aware."""

    PREVIEW_FPS = 10
    camera_list_ready = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self._config = AppConfig()
        self._lang = self._config.language
        self._overlay = BlurOverlay(self._config)

        self._detector = PostureDetector(self._config)
        self._detector.blur_ratio_changed.connect(self._on_blur_ratio)
        self._detector.status_changed.connect(self._on_status)
        self._detector.frame_ready.connect(self._on_frame)
        self._detector.away_changed.connect(self._overlay.set_away)
        self._detector.calibration_changed.connect(self._on_calibration_changed)
        self._detector.detection_stopped.connect(self._on_detection_stopped)
        self._detector.preview_enabled = True

        self._style_btns: dict[str, QPushButton] = {}
        self._swatch_btns: dict[str, QPushButton] = {}
        self._sliders: dict[str, tuple] = {}        # key -> (slider, capsule)
        self._row_labels: dict[str, QLabel] = {}    # key -> row label widget
        self._cameras: list[int] = []
        self._calibrated_state = self._detector.is_calibrated
        self._preview_buf = None
        self._last_frame_time = 0.0
        self._hint_timer = None
        self._status_raw = ""   # raw zh source of the current status message
        self._hotkey_ok = True  # registration state for the tooltip

        # Detection startup is deferred until camera enumeration finishes
        # (or a 4 s fallback) so the probe never fights the detection worker
        # over the same DSHOW device
        self._probe_done = False
        self._detection_pending = self._config.monitoring_enabled

        # Responsive window: restore saved size (clamped to the current
        # screen so a window saved on a big monitor can't open off-screen),
        # allow fullscreen + resize
        self.setMinimumSize(440, 520)
        w, h = self._config.window_width, self._config.window_height
        if w <= 0 or h <= 0:
            w, h = 480, 760
        w, h = self._clamp_to_screen(w, h)
        self.resize(w, h)

        self._build_ui()
        self._connect_controls()
        # The camera section may have started collapsed (auto-hide when a
        # calibration exists) — sync the worker's preview state with the
        # actual header state, since the toggled signal fired before
        # _on_cam_toggled was connected
        self._detector.preview_enabled = self._cam_section.header.isChecked()
        self._register_hotkey()
        self._setup_runtime()
        self._apply_theme()
        self._retranslate()

        # F11 fullscreen — window-level shortcut so it works even when a
        # combo popup is open or a child widget has focus
        self._f11 = QShortcut(QKeySequence("F11"), self)
        self._f11.setContext(Qt.ShortcutContext.WindowShortcut)
        self._f11.activated.connect(self._toggle_fullscreen)

        if self._detection_pending:
            self._set_status("正在搜索摄像头...")

        self.camera_list_ready.connect(self._on_cameras_found)
        self._enumerate_cameras()

        self._startup_timer = QTimer(self)
        self._startup_timer.setSingleShot(True)
        self._startup_timer.timeout.connect(self._maybe_start_detection)
        self._startup_timer.start(4000)

        self._update_toggle_text()
        self._on_calibration_changed(self._calibrated_state)

        if not self._config.calibration_saved:
            self._hint_timer = QTimer(self)
            self._hint_timer.setSingleShot(True)
            self._hint_timer.timeout.connect(self._show_calibration_hint)
            self._hint_timer.start(600)

    # ---- i18n / theme helpers ----

    def t(self, s: str) -> str:
        return translate(s, self._lang)

    @staticmethod
    def _clamp_to_screen(w: int, h: int) -> tuple[int, int]:
        screen = (
            QGuiApplication.screenAt(QGuiApplication.primaryScreen().availableGeometry().center())
            or QGuiApplication.primaryScreen()
        )
        avail = screen.availableGeometry()
        return min(w, avail.width()), min(h, avail.height())

    def _apply_theme(self):
        tk = THEME_TOKENS[self._config.theme]
        self._tokens = tk
        BrandSwitch.off_fill = QColor(*tk["switch_off"])
        BrandSwitch.text_color = QColor(*tk["switch_text"])
        self.setStyleSheet(self._build_stylesheet())
        for sw in (self._block_check, self._away_check, self._launch_check,
                   self._theme_switch):
            sw.update()
        self._preview_label.setStyleSheet(
            f"background: {tk['preview_bg']}; border-radius: 8px;"
        )
        self._update_swatch_styles()

    def _update_swatch_styles(self):
        """Swatch borders are inline styles — re-apply them per theme."""
        border = "#aaaaaa" if self._config.theme == "light" else "#555555"
        for (name, hexv), btn in self._swatch_btns.items():
            btn.setStyleSheet(
                f"QPushButton {{ background: {hexv}; border: 2px solid {border};"
                " border-radius: 5px; }"
                f"QPushButton:checked {{ border: 3px solid {BRAND_CYAN}; }}"
            )

    def _build_stylesheet(self) -> str:
        tk = self._tokens
        return f"""
            QMainWindow, QWidget {{ background: {tk['bg']}; color: {tk['text']}; font-size: 11pt; }}
            QWidget#settingsCard {{
                background: {tk['card']}; border: 1px solid {tk['border']};
                border-radius: 10px;
            }}
            QLabel#cardIcon {{ color: {BRAND_CYAN}; font-size: 11pt; font-weight: 600; }}
            QLabel#cardTitle {{ color: {tk['text']}; font-size: 12pt; font-weight: 600; }}
            QLabel#rowLabel {{ color: {tk['text']}; font-size: 11pt; }}
            QLabel#valueCapsule {{
                background: rgba(79,209,197,0.12); color: {BRAND_CYAN};
                border-radius: 9px; padding: 1px 6px; font-size: 10pt; font-weight: 500;
            }}
            QLabel#secondaryLabel {{ color: {tk['text_secondary']}; font-size: 10pt; }}
            QLabel#statusLabel {{ color: {tk['text_secondary']}; }}
            QWidget#segContainer {{
                background: {tk['seg_fill']}; border-radius: 6px;
            }}
            QPushButton {{
                background: {tk['btn_bg']}; border: 1px solid {tk['btn_border']};
                border-radius: 6px; padding: 5px 12px; color: {tk['btn_text']};
                text-align: center;
            }}
            QPushButton:hover {{ background: {tk['btn_hover']}; }}
            QPushButton#styleBtn {{
                background: transparent; border: none; border-radius: 4px;
                padding: 5px 0; font-size: 10pt; color: {tk['seg_btn_text']};
            }}
            QPushButton#styleBtn:hover {{ background: {tk['seg_hover']}; }}
            QPushButton#styleBtn:checked {{
                background: {BRAND_CYAN}; color: {ON_CYAN}; font-weight: 600;
            }}
            QPushButton#textToggleBtn {{
                background: {tk['chip_fill']}; border: 1px solid {tk['chip_border']};
                border-radius: 4px; padding: 4px 10px; font-size: 10pt;
                color: {tk['seg_btn_text']};
            }}
            QPushButton#textToggleBtn:checked {{
                background: rgba(79,209,197,0.15); border: 1px solid {BRAND_CYAN};
                color: {BRAND_CYAN};
            }}
            QPushButton#toggleBtn {{
                background: {BRAND_CYAN}; border: none; border-radius: 10px;
                color: {ON_CYAN}; font-size: 12pt; font-weight: 600;
                padding: 10px; text-align: center;
            }}
            QPushButton#toggleBtn:hover {{ background: #5fd9cd; }}
            QPushButton#toggleBtn:pressed {{ background: #3fb8ac; }}
            QPushButton#calibrateBtn {{
                background: rgba(79,209,197,0.1); border: 1px solid rgba(79,209,197,0.3);
                color: {BRAND_CYAN}; border-radius: 6px; font-size: 10pt;
            }}
            QPushButton#calibrateBtn:hover {{ background: rgba(79,209,197,0.18); }}
            QToolButton {{
                background: transparent; border: none;
                font-weight: 600; font-size: 12pt; padding: 2px 0;
                color: {tk['text']};
            }}
            QToolButton:hover {{ color: {BRAND_CYAN}; }}
            QSlider::groove:horizontal {{
                border: none; height: 4px; background: {tk['slider_track']};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: white; border: 1px solid rgba(0,0,0,0.12);
                width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{ border-color: {BRAND_CYAN}; }}
            QSlider::sub-page:horizontal {{
                background: rgba(79,209,197,0.85); border-radius: 2px;
            }}
            QLineEdit, QComboBox {{
                background: {tk['input_bg']}; border: 1px solid {tk['input_border']};
                border-radius: 6px; padding: 4px 8px; color: {tk['text']};
            }}
            QLineEdit:focus {{ border-color: {BRAND_CYAN}; }}
            QLineEdit#hotkeyEdit {{
                background: {tk['chip_fill']}; border: 1px solid {tk['chip_border']};
                border-radius: 4px; font-family: Consolas, "Courier New", monospace;
                font-size: 10pt; padding: 1px 4px; color: {tk['chip_text']};
            }}
            QLineEdit#hotkeyEdit[recording="true"] {{
                border-color: {BRAND_CYAN}; background: rgba(79,209,197,0.15);
                color: {BRAND_CYAN};
            }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QProgressBar {{
                border: none; border-radius: 3px; text-align: center;
                height: 6px; background: {tk['slider_track']};
                color: transparent;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f0a83c, stop:1 #e74c3c);
                border-radius: 3px;
            }}
            QScrollArea {{ border: none; background: {tk['bg']}; }}
            QScrollArea > QWidget > QWidget {{ background: {tk['bg']}; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
            QScrollBar::handle:vertical {{
                background: {tk['scroll_handle']}; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {tk['scroll_handle_hover']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        """

    def _retranslate(self):
        """Re-apply every user-visible string for the current language."""
        t = self.t
        self.setWindowTitle(t("WinDorso – 坐姿监测"))
        self._cam_section.header.setText(t("摄像头画面"))
        self._text_section.header.setText(t("文字提醒设置"))
        self._bar_label.setText(t("低头程度"))
        self._hk_label.setText(t("快捷键"))
        self._update_toggle_text()

        # calibration card
        self._cal_card.title_lbl.setText(t("校准"))
        self._cam_label.setText(t("摄像头"))
        self._cal_state_label.setText(t("校准状态"))
        self._calibrate_btn.setText(t("重新校准"))
        self._on_calibration_changed(self._calibrated_state)

        # detection card
        self._detect_card.title_lbl.setText(t("检测设置"))
        for key, zh in (("sensitivity", "灵敏度"), ("dead_zone", "容忍度"),
                        ("delay", "延迟(秒)"), ("detect_fps", "检测频率")):
            self._row_labels[key].setText(t(zh))
        self._detect_hint.setText(t(
            "灵敏度：越高，低头越容易触发提醒\n"
            "容忍度：允许轻微低头不提醒的范围，数值越高越宽松\n"
            "延迟：低头持续该时长后才触发提醒\n"
            "检测频率：每秒判断姿态的次数，越高反应越快"
        ))
        self._sliders["detect_fps"][0].setToolTip(
            t("频率越高反应越快，CPU 占用越高；松手后生效"))

        # style card
        self._style_card.title_lbl.setText(t("警告样式"))
        for key, btn in self._style_btns.items():
            btn.setText(t(STYLE_LABELS[key]))
        self._text_toggle_btn.setText(t("文字（可叠加）"))
        self._text_toggle_btn.setToolTip(t("在所选样式上叠加文字提醒"))

        # color card
        self._color_card.title_lbl.setText(t("颜色"))
        for (name, hexv), btn in self._swatch_btns.items():
            btn.setToolTip(t(name))
        self._custom_color_btn.setText(t("自定义颜色..."))
        self._update_color_label()

        # text reminder
        self._text_label.setText(t("文字"))
        self._text_edit.setPlaceholderText(t("输入提醒文字"))
        self._pos_label.setText(t("位置"))
        self._populate_pos_combo()

        # intensity
        self._intensity_card.title_lbl.setText(t("强度"))
        self._row_labels["intensity"].setText(t("覆盖强度"))

        # options
        self._options_card.title_lbl.setText(t("选项"))
        self._block_check.setText(t("低头时锁定鼠标（严格模式）"))
        self._away_check.setText(t("离开摄像头时自动模糊屏幕"))
        self._row_labels["away_intensity"].setText(t("离开模糊强度"))
        self._sliders["away_intensity"][0].setToolTip(
            t("按住拖动实时预览效果，松手后自动消失"))
        self._launch_check.setText(t("开机自启"))

        # general
        self._general_card.title_lbl.setText(t("通用"))
        self._theme_switch.setText(t("暗色模式"))
        self._lang_label.setText(t("语言"))

        # camera combo + hotkey
        self._populate_camera_combo()
        self._camera_combo.setToolTip(t("点击下拉选择，滚轮不会误改"))
        self._update_hotkey_tooltip()
        self._hotkey_edit.setPlaceholderText(t(
            "(点击后按下组合键：Ctrl/Alt/Shift/Win + 字母/数字/F1-F12，Esc 取消)"))

        # re-translate the current status message (if any)
        self._refresh_status_text()

        # sliders' value capsules with translated units
        self._sliders["detect_fps"][1].setText(
            t("{v}帧/秒").replace("{v}", str(self._config.detect_fps)))

    def _populate_camera_combo(self):
        self._camera_combo.blockSignals(True)
        self._camera_combo.clear()
        cur = self._config.camera_index
        if not self._cameras:
            # Probe finished but found nothing — don't leave "searching..."
            self._camera_combo.addItem(
                self.t("未检测到摄像头") if self._probe_done else self.t("搜索中..."), -1)
        else:
            # Never rewrite the config while the detector streams — that
            # would silently switch the persisted camera preference
            if cur not in self._cameras and not self._detector.is_running:
                cur = self._cameras[0]
                self._config.camera_index = cur
            for idx in self._cameras:
                self._camera_combo.addItem(self.t("摄像头 {n}").replace("{n}", str(idx)), idx)
            # Always list the active index so the UI tells the truth
            if self._camera_combo.findData(cur) < 0:
                self._camera_combo.addItem(self.t("摄像头 {n}").replace("{n}", str(cur)), cur)
            i = self._camera_combo.findData(cur)
            if i >= 0:
                self._camera_combo.setCurrentIndex(i)
        self._camera_combo.blockSignals(False)

    def _populate_pos_combo(self):
        cur = self._config.overlay_text_position
        self._pos_combo.blockSignals(True)
        self._pos_combo.clear()
        for label, key in POSITIONS:
            self._pos_combo.addItem(self.t(label), key)
        idx = self._pos_combo.findData(cur)
        if idx >= 0:
            self._pos_combo.setCurrentIndex(idx)
        self._pos_combo.blockSignals(False)

    # ---- detection startup (serialized after camera enumeration) ----

    def _maybe_start_detection(self):
        if not self._detection_pending:
            return
        if not self._probe_done and self._startup_timer.isActive():
            return
        self._detection_pending = False
        self._startup_timer.stop()
        self._detector.start()
        self._update_toggle_text()

    # ---- runtime helpers ----

    def _setup_runtime(self):
        # Blur-bar value animation: easeOut (ScoreRing's 0.5 s policy)
        self._bar_anim = QVariantAnimation(self)
        self._bar_anim.setDuration(300)
        self._bar_anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.OutQuad))
        self._bar_anim.valueChanged.connect(lambda v: self._blur_bar.setValue(int(v)))

        # Debounced overlay refresh — coalesces bursts of style/color/slider
        # changes into single repaints so live switching stays smooth
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(80)
        self._refresh_timer.timeout.connect(self._overlay.refresh)

    def _schedule_refresh(self):
        self._refresh_timer.start()

    # ---- status message (stashed raw so language switches re-translate) ----

    def _set_status(self, raw: str):
        self._status_raw = raw
        self._refresh_status_text()

    def _refresh_status_text(self):
        if not self._status_raw:
            return
        text = translate(self._status_raw, self._lang)
        if "{hk}" in text:
            text = text.replace("{hk}", self._hotkey_text())
        self._status_label.setText(text)

    # ---- hotkey ----

    def _hotkey_text(self) -> str:
        return hotkey_label(self._config.hotkey_modifiers, self._config.hotkey_key)

    def _register_hotkey(self):
        app = QApplication.instance()
        self._hotkey_filter = HotkeyFilter(self._on_toggle)
        app.installNativeEventFilter(self._hotkey_filter)
        self._apply_hotkey(self._config.hotkey_modifiers, self._config.hotkey_key)

    def _apply_hotkey(self, mods: int, vk: int) -> bool:
        """Re-register the OS hotkey; persists only on success, otherwise the
        previous working combo is restored and re-registered."""
        _user32.UnregisterHotKey(None, HOTKEY_ID)
        ok = bool(_user32.RegisterHotKey(None, HOTKEY_ID, mods, vk))
        if ok:
            self._config.hotkey_modifiers = mods
            self._config.hotkey_key = vk
        else:
            _user32.RegisterHotKey(
                None, HOTKEY_ID, self._config.hotkey_modifiers, self._config.hotkey_key
            )
        self._hotkey_edit.setText(self._hotkey_text())
        self._update_toggle_text()
        self._hotkey_ok = ok
        self._update_hotkey_tooltip()
        return ok

    def _update_hotkey_tooltip(self):
        if self._hotkey_ok:
            self._hotkey_edit.setToolTip(self.t("点击后按下新的组合键，Esc 取消"))
        else:
            self._hotkey_edit.setToolTip(self.t("注册失败：快捷键可能被其他程序占用"))

    def _reapply_saved_hotkey(self):
        _user32.RegisterHotKey(
            None, HOTKEY_ID, self._config.hotkey_modifiers, self._config.hotkey_key
        )

    def _update_toggle_text(self):
        self._toggle_btn.setText(
            self.t("停止监测") if self._detector.is_running else self.t("开始监测")
        )

    def _start_hotkey_capture(self):
        if self._hotkey_recording:
            return
        self._hotkey_recording = True
        _user32.UnregisterHotKey(None, HOTKEY_ID)  # avoid double-fire
        self._hotkey_edit.clear()  # ghost placeholder rules show inside the box
        self._hotkey_edit.setProperty("recording", True)
        self._hotkey_edit.style().unpolish(self._hotkey_edit)
        self._hotkey_edit.style().polish(self._hotkey_edit)
        self._key_capture = KeyCaptureFilter(self._on_hotkey_captured, self._cancel_hotkey_capture)
        QApplication.instance().installEventFilter(self._key_capture)

    def _end_hotkey_capture(self):
        QApplication.instance().removeEventFilter(self._key_capture)
        self._hotkey_recording = False
        self._hotkey_edit.setProperty("recording", False)
        self._hotkey_edit.style().unpolish(self._hotkey_edit)
        self._hotkey_edit.style().polish(self._hotkey_edit)
        self._hotkey_edit.setText(self._hotkey_text())

    def _on_hotkey_captured(self, qt_mods, qt_key):
        self._end_hotkey_capture()
        if qt_mods & Qt.KeyboardModifier.KeypadModifier:
            self._set_status("⚠ 不支持小键盘按键，请使用主键盘字母/数字/F1-F12")
            self._reapply_saved_hotkey()
            return
        mods = qt_mods_to_win(qt_mods)
        vk = qt_key_to_vk(qt_key)
        if vk == 0:
            self._set_status("⚠ 快捷键仅支持字母/数字/F1-F12")
            self._reapply_saved_hotkey()
            return
        if mods == 0:
            self._set_status("⚠ 快捷键需包含 Ctrl/Alt/Shift/Win")
            self._reapply_saved_hotkey()
            return
        if self._apply_hotkey(mods, vk):
            self._set_status("快捷键已更新为 {hk}")
        else:
            self._set_status("⚠ 快捷键注册失败，已恢复原快捷键")

    def _cancel_hotkey_capture(self):
        self._end_hotkey_capture()
        self._reapply_saved_hotkey()
        self._set_status("已取消快捷键修改")

    def _unregister_hotkey(self):
        _user32.UnregisterHotKey(None, HOTKEY_ID)

    # ---- camera enumeration ----

    def _enumerate_cameras(self):
        # Runs BEFORE detection starts (see _maybe_start_detection), so no
        # DSHOW device is ever opened by two consumers at once
        def worker():
            cams = []
            for i in range(6):
                with camera_lock:
                    try:
                        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                        if cap is not None and cap.isOpened():
                            cams.append(i)
                            cap.release()
                        elif cap is not None:
                            cap.release()
                    except cv2.error:
                        pass  # probe failure on a virtual device — skip it
            self.camera_list_ready.emit(cams)

        threading.Thread(target=worker, daemon=True).start()

    def _on_cameras_found(self, cams: list):
        self._cameras = cams
        self._populate_camera_combo()
        self._probe_done = True
        self._maybe_start_detection()

    # ---- UI ----

    def _build_ui(self):
        t = self.t
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # --- camera preview (collapsible, responsive height) ---
        self._cam_section = CollapsibleSection(t("摄像头画面"))
        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(200)
        self._preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._cam_section.content_layout.addWidget(self._preview_label)
        # Auto-hide the camera on startup when a calibration already exists
        self._cam_section.header.setChecked(
            self._config.show_camera_preview and not self._config.calibration_saved
        )
        root.addWidget(self._cam_section)

        # --- slouch level bar ---
        bar_row = QHBoxLayout()
        self._bar_label = QLabel(t("低头程度"))
        self._bar_label.setObjectName("rowLabel")
        bar_row.addWidget(self._bar_label)
        self._blur_bar = QProgressBar()
        self._blur_bar.setRange(0, 100)
        self._blur_bar.setValue(0)
        self._blur_bar.setFormat("%p%")
        bar_row.addWidget(self._blur_bar, stretch=1)
        root.addLayout(bar_row)

        # --- monitor toggle (primary CTA) + hotkey chip ---
        self._toggle_btn = QPushButton()
        self._toggle_btn.setObjectName("toggleBtn")
        self._toggle_btn.setMinimumHeight(38)
        root.addWidget(self._toggle_btn)

        hk_row = QHBoxLayout()
        self._hk_label = QLabel(t("快捷键"))
        self._hk_label.setObjectName("rowLabel")
        hk_row.addWidget(self._hk_label)
        self._hotkey_edit = HotkeyEdit(self._hotkey_text(), self._start_hotkey_capture)
        self._hotkey_edit.setObjectName("hotkeyEdit")
        self._hotkey_edit.setFixedWidth(130)
        self._hotkey_edit.setFixedHeight(24)
        hk_row.addWidget(self._hotkey_edit)
        hk_row.addStretch()
        root.addLayout(hk_row)
        self._hotkey_recording = False

        self._status_label = QLabel()
        self._status_label.setObjectName("statusLabel")
        self._status_label.setWordWrap(True)
        root.addWidget(self._status_label)

        # --- calibration card ---
        self._cal_card = SettingsCard("◎", t("校准"))
        cam_row = QHBoxLayout()
        self._cam_label = QLabel(t("摄像头"))
        self._cam_label.setObjectName("rowLabel")
        cam_row.addWidget(self._cam_label)
        self._camera_combo = NoWheelComboBox()
        cam_row.addWidget(self._camera_combo, stretch=1)
        self._cal_card.content_layout.addLayout(cam_row)

        status_row = QHBoxLayout()
        self._cal_state_label = QLabel(t("校准状态"))
        self._cal_state_label.setObjectName("rowLabel")
        status_row.addWidget(self._cal_state_label)
        self._cal_status = QLabel()
        status_row.addWidget(self._cal_status)
        status_row.addStretch()
        self._cal_card.content_layout.addLayout(status_row)

        self._calibrate_btn = QPushButton(t("重新校准"))
        self._calibrate_btn.setObjectName("calibrateBtn")
        self._calibrate_btn.setMinimumHeight(30)
        self._cal_card.content_layout.addWidget(self._calibrate_btn)

        root.addWidget(self._cal_card)

        # --- detection settings card ---
        self._detect_card = SettingsCard("⚙", t("检测设置"))
        self._detect_card.content_layout.addLayout(
            self._make_slider("sensitivity", "灵敏度", 1, 5, self._config.sensitivity)
        )
        self._detect_card.content_layout.addLayout(
            self._make_slider("dead_zone", "容忍度", 1, 5, self._config.dead_zone)
        )
        self._detect_card.content_layout.addLayout(
            self._make_slider("delay", "延迟(秒)", 0, 10, self._config.delay_tenths)
        )
        self._sliders["delay"][1].setText(f"{self._config.delay_tenths / 10:.1f}")

        self._detect_card.content_layout.addLayout(
            self._make_slider("detect_fps", "检测频率", 5, 30,
                              self._config.detect_fps, val_width=60, step=5)
        )
        self._sliders["detect_fps"][1].setText(
            t("{v}帧/秒").replace("{v}", str(self._config.detect_fps)))

        self._detect_hint = QLabel()
        self._detect_hint.setObjectName("secondaryLabel")
        self._detect_card.content_layout.addWidget(self._detect_hint)

        root.addWidget(self._detect_card)

        # --- warning style card (segmented control) ---
        self._style_card = SettingsCard("⚠", t("警告样式"))

        seg_container = QWidget()
        seg_container.setObjectName("segContainer")
        seg_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        seg_layout = QHBoxLayout(seg_container)
        seg_layout.setContentsMargins(2, 2, 2, 2)
        seg_layout.setSpacing(0)
        current = self._config.warning_style
        for key in STYLE_ORDER:
            btn = QPushButton()
            btn.setObjectName("styleBtn")
            btn.setCheckable(True)
            btn.setChecked(key == current)
            btn.setMinimumHeight(26)
            btn.clicked.connect(lambda checked, k=key: self._on_style(k))
            self._style_btns[key] = btn
            seg_layout.addWidget(btn, stretch=1)
        self._style_card.content_layout.addWidget(seg_container)

        # Combinable text toggle (chip-style checkable button)
        self._text_toggle_btn = QPushButton(t("文字（可叠加）"))
        self._text_toggle_btn.setObjectName("textToggleBtn")
        self._text_toggle_btn.setCheckable(True)
        self._text_toggle_btn.setChecked(self._config.overlay_text_enabled)
        self._text_toggle_btn.setMinimumHeight(26)
        text_toggle_row = QHBoxLayout()
        text_toggle_row.addWidget(self._text_toggle_btn)
        text_toggle_row.addStretch()
        self._style_card.content_layout.addLayout(text_toggle_row)

        root.addWidget(self._style_card)

        # --- color card ---
        self._color_card = SettingsCard("◉", t("颜色"))
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (name, hexv) in enumerate(NAMED_COLORS):
            btn = QPushButton()
            btn.setFixedSize(52, 30)
            btn.setCheckable(True)
            btn.setToolTip(t(name))
            btn.clicked.connect(lambda checked, idx=i: self._on_swatch(idx))
            grid.addWidget(btn, i // 4, i % 4)
            self._swatch_btns[(name, hexv)] = btn
        self._update_swatch_styles()
        self._color_card.content_layout.addLayout(grid)

        custom_row = QHBoxLayout()
        self._custom_color_btn = QPushButton(t("自定义颜色..."))
        self._custom_color_btn.clicked.connect(self._pick_color)
        custom_row.addWidget(self._custom_color_btn)
        self._color_label = QLabel()
        self._color_label.setObjectName("secondaryLabel")
        custom_row.addWidget(self._color_label, stretch=1)
        self._color_card.content_layout.addLayout(custom_row)

        root.addWidget(self._color_card)

        # --- text reminder (collapsible; only visible when the toggle is on) ---
        self._text_section = CollapsibleSection(t("文字提醒设置"))
        tl = self._text_section.content_layout

        text_row = QHBoxLayout()
        self._text_label = QLabel(t("文字"))
        self._text_label.setObjectName("rowLabel")
        text_row.addWidget(self._text_label)
        self._text_edit = QLineEdit(self._config.overlay_text_content)
        self._text_edit.setMaxLength(20)
        text_row.addWidget(self._text_edit, stretch=1)
        tl.addLayout(text_row)

        pos_row = QHBoxLayout()
        self._pos_label = QLabel(t("位置"))
        self._pos_label.setObjectName("rowLabel")
        pos_row.addWidget(self._pos_label)
        self._pos_combo = NoWheelComboBox()
        pos_row.addWidget(self._pos_combo, stretch=1)
        tl.addLayout(pos_row)

        self._text_section.setVisible(self._config.overlay_text_enabled)
        self._text_section.header.setChecked(True)
        root.addWidget(self._text_section)

        # --- intensity card ---
        self._intensity_card = SettingsCard("▮", t("强度"))
        self._intensity_card.content_layout.addLayout(
            self._make_slider("intensity", "覆盖强度", 1, 10, self._config.overlay_intensity)
        )
        root.addWidget(self._intensity_card)

        # --- options card ---
        self._options_card = SettingsCard("⏻", t("选项"))

        self._block_check = BrandSwitch(t("低头时锁定鼠标（严格模式）"))
        self._block_check.setChecked(self._config.overlay_block_mouse)
        self._options_card.content_layout.addWidget(self._block_check)

        self._away_check = BrandSwitch(t("离开摄像头时自动模糊屏幕"))
        self._away_check.setChecked(self._config.blur_when_away)
        self._options_card.content_layout.addWidget(self._away_check)

        self._options_card.content_layout.addLayout(
            self._make_slider("away_intensity", "离开模糊强度", 1, 10,
                              self._config.away_intensity)
        )

        self._launch_check = BrandSwitch(t("开机自启"))
        self._launch_check.setChecked(self._config.launch_at_login)
        self._options_card.content_layout.addWidget(self._launch_check)

        root.addWidget(self._options_card)

        # --- general card (theme + language) ---
        self._general_card = SettingsCard("◐", t("通用"))

        self._theme_switch = BrandSwitch(t("暗色模式"))
        self._theme_switch.setChecked(self._config.theme == "dark")
        self._general_card.content_layout.addWidget(self._theme_switch)

        lang_row = QHBoxLayout()
        self._lang_label = QLabel(t("语言"))
        self._lang_label.setObjectName("rowLabel")
        lang_row.addWidget(self._lang_label)
        self._lang_combo = NoWheelComboBox()
        self._lang_combo.addItem("中文", "zh")
        self._lang_combo.addItem("English", "en")
        idx = self._lang_combo.findData(self._config.language)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)
        lang_row.addWidget(self._lang_combo, stretch=1)
        self._general_card.content_layout.addLayout(lang_row)

        root.addWidget(self._general_card)

        # No trailing stretch: the Expanding camera preview absorbs the
        # extra height in tall/fullscreen windows

        # --- wrap in scroll area ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setCentralWidget(scroll)

    def _make_slider(self, key, label_zh, lo, hi, value, val_width=40, step=1):
        """Compact slider row: 11pt label, 4px track, 10pt brandCyan value
        capsule (Dorso CompactSlider)."""
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(self.t(label_zh))
        lbl.setObjectName("rowLabel")
        lbl.setFixedWidth(82)
        row.addWidget(lbl)
        slider = NoWheelSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setSingleStep(step)
        slider.setPageStep(step)
        slider.setValue(value)
        slider.setFixedHeight(22)
        row.addWidget(slider, stretch=1)
        val_lbl = QLabel(str(value))
        val_lbl.setObjectName("valueCapsule")
        val_lbl.setFixedWidth(val_width)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(val_lbl)
        self._sliders[key] = (slider, val_lbl)
        self._row_labels[key] = lbl
        return row

    def _connect_controls(self):
        self._toggle_btn.clicked.connect(self._on_toggle)
        self._calibrate_btn.clicked.connect(self._on_calibrate)
        self._cam_section.header.toggled.connect(self._on_cam_toggled)
        self._camera_combo.currentIndexChanged.connect(self._on_camera_changed)
        self._block_check.toggled.connect(self._on_block_toggled)
        self._away_check.toggled.connect(self._on_away_toggled)
        self._launch_check.toggled.connect(self._on_launch_toggled)
        self._text_toggle_btn.toggled.connect(self._on_text_toggle)
        self._theme_switch.toggled.connect(self._on_theme_toggled)
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)

        self._sliders["sensitivity"][0].valueChanged.connect(self._on_sensitivity)
        self._sliders["dead_zone"][0].valueChanged.connect(self._on_dead_zone)
        self._sliders["delay"][0].valueChanged.connect(self._on_delay)
        self._sliders["intensity"][0].valueChanged.connect(self._on_intensity)
        self._sliders["away_intensity"][0].valueChanged.connect(self._on_away_intensity)
        self._sliders["detect_fps"][0].valueChanged.connect(self._on_detect_fps)
        self._sliders["detect_fps"][0].sliderReleased.connect(self._on_detect_fps_released)

        # Away preview: hold to preview, release to fade out
        self._sliders["away_intensity"][0].sliderPressed.connect(self._on_away_preview_start)
        self._sliders["away_intensity"][0].sliderReleased.connect(self._on_away_preview_end)

        self._text_edit.textChanged.connect(self._on_text_changed)
        self._pos_combo.currentIndexChanged.connect(self._on_pos_changed)

    # ---- theme / language handlers ----

    def _on_theme_toggled(self, checked):
        self._config.theme = "dark" if checked else "light"
        self._apply_theme()

    def _on_language_changed(self, index: int):
        key = self._lang_combo.itemData(index)
        if key and key != self._lang:
            self._lang = key
            self._config.language = key
            self._retranslate()

    # ---- calibration hint ----

    def _show_calibration_hint(self):
        if not self.isVisible():
            return  # window was closed before the timer fired
        QMessageBox.information(
            self, self.t("首次使用"),
            self.t(
                "请保持正确坐姿，程序将自动完成校准。\n"
                "校准完成后会保存为标准，以后每次启动都自动使用。\n"
                "如需更换标准，点击「重新校准」。"
            )
        )

    # ---- color helpers ----

    def _pick_color(self):
        color = QColorDialog.getColor(
            QColor(self._config.overlay_color), self, self.t("选择警告颜色")
        )
        if color.isValid():
            self._config.overlay_color = color.name()
            self._update_color_label()
            self._schedule_refresh()

    def _update_color_label(self):
        c = self._config.overlay_color.upper()
        name = None
        for n, h in NAMED_COLORS:
            if h.upper() == c:
                name = n
                break
        display = self.t(name) if name else c
        self._color_label.setText(
            self.t("当前：{name}").replace("{name}", display)
        )
        for (n, hexv), btn in self._swatch_btns.items():
            btn.blockSignals(True)
            btn.setChecked(hexv.upper() == c)
            btn.blockSignals(False)

    # ---- slots ----

    @pyqtSlot(float)
    def _on_blur_ratio(self, ratio: float):
        if ratio > 0 and not self._detector.is_running:
            return  # stale queued emission after stop — never re-blur
        self._overlay.set_blur_ratio(ratio)
        # Smoothly animate the progress bar toward the new value
        self._bar_anim.stop()
        self._bar_anim.setStartValue(self._blur_bar.value())
        self._bar_anim.setEndValue(int(ratio * 100))
        self._bar_anim.start()

    @pyqtSlot()
    def _on_detection_stopped(self):
        """Worker exited for any reason — resync UI and clear the overlay."""
        self._overlay.set_blur_ratio(0.0)
        self._overlay.set_away(False)
        self._update_toggle_text()

    @pyqtSlot(str)
    def _on_status(self, text: str):
        self._set_status(text)

    @pyqtSlot(np.ndarray)
    def _on_frame(self, frame: np.ndarray):
        # Time-based throttle — independent of the emitter's frame rate
        now = time.monotonic()
        if now - self._last_frame_time < 1.0 / self.PREVIEW_FPS:
            return
        if not self.isVisible() or not self._cam_section.content.isVisible():
            return
        h, w = frame.shape[:2]
        if h <= 1:
            # Blank sentinel: clear the stale frame, don't leave a frozen one
            self._preview_label.clear()
            return
        rgb = frame[..., ::-1].copy()
        # Hold the buffer so QImage/QPixmap never dangle after GC
        self._preview_buf = rgb
        qimage = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimage)
        # Cap the upscale target — fullscreen-sized smooth upscaling of a
        # 640x480 frame every frame is pure CPU waste and looks soft anyway
        target_w = min(self._preview_label.width(), 1280)
        target_h = min(self._preview_label.height(), 960)
        self._preview_label.setPixmap(pixmap.scaled(
            QSize(target_w, target_h), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        self._last_frame_time = now

    def _on_toggle(self):
        # A manual toggle cancels any pending deferred auto-start and
        # persists the choice so the next launch respects it
        self._detection_pending = False
        self._startup_timer.stop()
        running = self._detector.is_running
        if running:
            self._detector.stop()
            self._overlay.set_blur_ratio(0.0)  # clear any residual dim
            self._overlay.set_away(False)
        else:
            self._detector.start()
        self._config.monitoring_enabled = not running
        self._update_toggle_text()

    def _on_calibrate(self):
        # Auto-expand camera preview so the user can see themselves
        self._cam_section.header.setChecked(True)
        self._detector.recalibrate()

    def _on_cam_toggled(self, checked):
        self._config.show_camera_preview = checked
        self._detector.preview_enabled = checked

    def _on_text_toggle(self, checked):
        self._config.overlay_text_enabled = checked
        self._text_section.setVisible(checked)
        if checked:
            self._text_section.header.setChecked(True)  # auto-expand
        self._schedule_refresh()

    def _on_camera_changed(self, index: int):
        idx = self._camera_combo.itemData(index)
        if idx is None or idx < 0 or idx == self._config.camera_index:
            return
        self._config.camera_index = idx
        if self._detector.is_running:
            self._detector.stop()
            self._detector.start()
            self._update_toggle_text()

    def _on_calibration_changed(self, calibrated: bool):
        self._calibrated_state = calibrated
        if calibrated:
            self._cal_status.setText(self.t("● 已校准"))
            self._cal_status.setStyleSheet("color: #4caf50; font-size: 10pt;")
        else:
            self._cal_status.setText(self.t("● 未校准"))
            self._cal_status.setStyleSheet("color: #e6a23c; font-size: 10pt;")

    def _on_style(self, key: str):
        self._config.warning_style = key
        for k, btn in self._style_btns.items():
            btn.setChecked(k == key)
        self._schedule_refresh()

    def _on_swatch(self, idx: int):
        _, hexv = NAMED_COLORS[idx]
        self._config.overlay_color = hexv
        self._update_color_label()
        self._schedule_refresh()

    def _on_sensitivity(self, value):
        self._config.sensitivity = value
        self._sliders["sensitivity"][1].setText(str(value))

    def _on_dead_zone(self, value):
        self._config.dead_zone = value
        self._sliders["dead_zone"][1].setText(str(value))

    def _on_delay(self, value):
        self._config.delay_tenths = value
        self._sliders["delay"][1].setText(f"{value / 10:.1f}")

    def _on_detect_fps(self, value):
        v = max(5, min(30, int(round(value / 5.0) * 5)))
        self._config.detect_fps = v
        self._sliders["detect_fps"][1].setText(
            self.t("{v}帧/秒").replace("{v}", str(v)))
        slider = self._sliders["detect_fps"][0]
        if slider.value() != v:
            slider.blockSignals(True)
            slider.setValue(v)
            slider.blockSignals(False)

    def _on_detect_fps_released(self):
        """Apply the new frame interval once, on slider release — restarting
        the camera on every drag tick would freeze the GUI."""
        if self._detector.is_running:
            self._detector.stop()
            self._detector.start()
            self._update_toggle_text()

    def _on_intensity(self, value):
        self._config.overlay_intensity = value
        self._sliders["intensity"][1].setText(str(value))
        self._schedule_refresh()

    def _on_away_intensity(self, value):
        self._config.away_intensity = value
        self._sliders["away_intensity"][1].setText(str(value))
        self._schedule_refresh()

    def _on_away_preview_start(self):
        """Hold-to-preview: show the away dim for the whole drag."""
        self._overlay.flash_away(60000)

    def _on_away_preview_end(self):
        """Fade out shortly after release."""
        self._overlay.flash_away(800)

    def _on_text_changed(self, text: str):
        self._config.overlay_text_content = text
        self._schedule_refresh()

    def _on_pos_changed(self, index: int):
        key = self._pos_combo.itemData(index)
        if key:
            self._config.overlay_text_position = key
            self._schedule_refresh()

    def _on_block_toggled(self, checked):
        self._config.overlay_block_mouse = checked
        self._schedule_refresh()

    def _on_away_toggled(self, checked):
        self._config.blur_when_away = checked

    def _on_launch_toggled(self, checked):
        self._config.launch_at_login = checked
        self._set_launch_at_login(checked)

    def _set_launch_at_login(self, enable: bool):
        """Add or remove from Windows startup registry."""
        import os
        import winreg

        pythonw = os.path.join(sys.prefix, "pythonw.exe")
        script = os.path.abspath(sys.argv[0])
        value = f'"{pythonw}" "{script}"'

        key = winreg.HKEY_CURRENT_USER
        sub = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            reg = winreg.OpenKey(key, sub, 0, winreg.KEY_SET_VALUE)
            if enable:
                winreg.SetValueEx(reg, "WinDorso", 0, winreg.REG_SZ, value)
            else:
                winreg.DeleteValue(reg, "WinDorso")
            winreg.CloseKey(reg)
        except OSError:
            pass

    # ---- fullscreen + window sizing ----

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def closeEvent(self, event):
        if self._hint_timer is not None:
            self._hint_timer.stop()
        # Persist the window size (skip when maximized/fullscreen)
        if not self.isMaximized() and not self.isFullScreen():
            self._config.window_width = self.width()
            self._config.window_height = self.height()
        self._unregister_hotkey()
        self._detector.stop()
        self._overlay.close_all()
        super().closeEvent(event)
