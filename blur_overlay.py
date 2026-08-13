"""Per-monitor posture feedback overlay.

Warning styles (customizable color):
  "blur"       — dark dim with soft vignette
  "glow"       — colored radial glow closing in from the edges
  "border"     — colored border frame that thickens with slouch
  "fullscreen" — fullscreen colored fill with subtle depth gradient
  "none"       — no visual style (text layer may still be on)

Text reminder is a separate combinable layer (config.overlay_text_enabled).
"Away" state: strong neutral dark dim.
Mouse click-through via native WS_EX_TRANSPARENT; config.overlay_block_mouse
removes it so clicks are captured.

Visibility is driven by a single _should_show() predicate so the show/hide
rule can never diverge between set_dim_ratio / set_away / _end_flash.
"""

import ctypes
import math
from ctypes import wintypes

from PyQt6.QtCore import Qt, QObject, QPointF, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QRadialGradient, QBrush, QFont
from PyQt6.QtWidgets import QApplication, QWidget

from config import AppConfig

# ---- native click-through ----

user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

GetWindowLongW = user32.GetWindowLongW
GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
GetWindowLongW.restype = ctypes.c_long

SetWindowLongW = user32.SetWindowLongW
SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
SetWindowLongW.restype = ctypes.c_long

SetWindowPos = user32.SetWindowPos
SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
SetWindowPos.restype = wintypes.BOOL

# ---- text layout (module-level so paint doesn't rebuild it) ----

_AL_L = Qt.AlignmentFlag.AlignLeft
_AL_HC = Qt.AlignmentFlag.AlignHCenter
_AL_R = Qt.AlignmentFlag.AlignRight
_AL_T = Qt.AlignmentFlag.AlignTop
_AL_VC = Qt.AlignmentFlag.AlignVCenter
_AL_B = Qt.AlignmentFlag.AlignBottom

# 9-cell grid: key -> alignment flags; rect computed by _cell_rect()
_TEXT_ALIGN = {
    "tl": _AL_L | _AL_T,
    "tc": _AL_HC | _AL_T,
    "tr": _AL_R | _AL_T,
    "cl": _AL_L | _AL_VC,
    "cc": _AL_HC | _AL_VC,
    "cr": _AL_R | _AL_VC,
    "bl": _AL_L | _AL_B,
    "bc": _AL_HC | _AL_B,
    "br": _AL_R | _AL_B,
}


def _cell_rect(key: str, w: int, h: int, margin: int):
    if key == "tl":
        return (margin, margin, w // 2 - margin, h // 3 - margin)
    if key == "tc":
        return (0, margin, w, h // 3 - margin)
    if key == "tr":
        return (0, margin, w - margin, h // 3 - margin)
    if key == "cl":
        return (margin, 0, w // 2 - margin, h)
    if key == "cc":
        return (0, 0, w, h)
    if key == "cr":
        return (0, 0, w - margin, h)
    if key == "bl":
        return (margin, 0, w // 2 - margin, h - margin)
    if key == "bc":
        return (0, 0, w, h - margin)
    if key == "br":
        return (0, 0, w - margin, h - margin)
    return (0, 0, w, h)


def _ease_out(t: float) -> float:
    """Quadratic ease-out: subtle at low slouch, strong at high slouch."""
    return 1.0 - (1.0 - t) ** 2


def _safe_alpha(v, multiplier):
    if math.isnan(v):
        return 0
    return max(0, min(255, int(v * multiplier)))


def _with_alpha(c: QColor, alpha: int) -> QColor:
    return QColor(c.red(), c.green(), c.blue(), alpha)


class DimScreen(QWidget):
    """Fullscreen overlay window for one monitor."""

    def __init__(self, screen_geometry, config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._ratio = 0.0
        self._away = False
        self._flash_active = False
        self._flash_timer: QTimer | None = None
        self._last_block_mouse = None  # dedupe native style updates

        self._text_font: QFont | None = None
        self._text_font_size = 0

        self.setGeometry(screen_geometry)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("background: transparent;")
        self.hide()

    # ---- visibility state machine (single source of truth) ----

    def _should_show(self) -> bool:
        if self._away or self._flash_active:
            return True
        if self._ratio <= 0.001:
            return False
        if self._config.warning_style != "none":
            return True
        return self._config.overlay_text_enabled

    def _sync_visibility(self):
        if self._should_show():
            if not self.isVisible():
                self.show()
            self.update()
            self.raise_()
        else:
            if self.isVisible():
                self.hide()

    # ---- state & native style ----

    def _color(self) -> QColor:
        return QColor(self._config.overlay_color)

    def _update_native_style(self):
        """Toggle WS_EX_TRANSPARENT — skips Win32 calls when unchanged."""
        block = self._config.overlay_block_mouse
        if block == self._last_block_mouse:
            return
        self._last_block_mouse = block
        hwnd = int(self.winId())
        ex = GetWindowLongW(hwnd, GWL_EXSTYLE)
        if block:
            ex &= ~WS_EX_TRANSPARENT
        else:
            ex |= WS_EX_TRANSPARENT | WS_EX_LAYERED
        SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
        # SWP_FRAMECHANGED makes the extended-style change take effect
        # reliably on an already-visible window
        SetWindowPos(hwnd, None, 0, 0, 0, 0,
                     SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)

    def showEvent(self, event):
        super().showEvent(event)
        # Fresh HWND — force a re-apply so click-through can never be lost
        # after Qt recreates the native window
        self._last_block_mouse = None
        self._update_native_style()

    def set_dim_ratio(self, ratio: float):
        """Slouch-triggered overlay ratio 0.0–1.0."""
        if math.isnan(ratio):
            ratio = 0.0
        ratio = max(0.0, min(1.0, ratio))
        if ratio == self._ratio:
            return
        self._ratio = ratio
        self._sync_visibility()

    def set_away(self, active: bool):
        if active == self._away:
            return
        self._away = active
        self._sync_visibility()

    # ---- away flash preview ----

    def flash_away(self, duration_ms: int):
        """Temporarily show the away dim without touching the real away state.

        Re-calling restarts the countdown (used while dragging a slider).
        """
        self._flash_active = True
        self._sync_visibility()
        if self._flash_timer is None:
            self._flash_timer = QTimer(self)
            self._flash_timer.setSingleShot(True)
            self._flash_timer.timeout.connect(self._end_flash)
        self._flash_timer.start(duration_ms)

    def _end_flash(self):
        self._flash_active = False
        self._sync_visibility()

    # ---- painting ----

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Away state: strong neutral dark, no color, no text
        if self._away or self._flash_active:
            intensity = self._config.away_intensity_normalized
            alpha = int(100 + intensity * 155)  # 100–255, scales with slider
            painter.fillRect(self.rect(), QColor(0, 0, 0, alpha))
            painter.end()
            return

        if self._ratio <= 0.0:
            painter.end()
            return

        w, h = self.rect().width(), self.rect().height()
        intensity = self._config.intensity_normalized
        color = self._color()
        r = _ease_out(self._ratio)

        style = self._config.warning_style
        if style != "none":
            if style == "blur":
                self._paint_blur(painter, w, h, r, intensity)
            elif style == "glow":
                self._paint_glow(painter, w, h, r, intensity, color)
            elif style == "border":
                self._paint_border(painter, w, h, r, intensity, color)
            elif style == "fullscreen":
                self._paint_full(painter, w, h, r, intensity, color)

        # Text reminder is an independent layer combinable with any style
        if self._config.overlay_text_enabled:
            self._paint_text(painter, w, h, r)

        painter.end()

    # ---- style paints ----

    def _paint_blur(self, painter, w, h, r, intensity):
        base = _safe_alpha(r * intensity, 160)
        if base > 0:
            painter.fillRect(self.rect(), QColor(0, 0, 0, base))

        edge = _safe_alpha(r * intensity, 90)
        if edge > 0:
            gradient = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.55)
            gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
            gradient.setColorAt(0.75, QColor(0, 0, 0, 0))
            gradient.setColorAt(1.0, QColor(0, 0, 0, edge))
            painter.fillRect(self.rect(), QBrush(gradient))

    def _paint_glow(self, painter, w, h, r, intensity, color):
        max_r = max(w, h) * 0.75
        min_r = max(w, h) * 0.12
        radius = max_r - r * intensity * (max_r - min_r)

        gradient = QRadialGradient(QPointF(w / 2, h * 0.42), radius)
        gradient.setColorAt(0.0, _with_alpha(color, 0))
        gradient.setColorAt(0.45, _with_alpha(color, 0))
        gradient.setColorAt(0.72, _with_alpha(color, _safe_alpha(r * intensity, 90)))
        gradient.setColorAt(0.9, _with_alpha(color, _safe_alpha(r * intensity, 170)))
        gradient.setColorAt(1.0, _with_alpha(color, _safe_alpha(r * intensity, 220)))

        painter.fillRect(self.rect(), QBrush(gradient))

    def _paint_border(self, painter, w, h, r, intensity, color):
        """Border frame: sharp outer corners (screen edges), small inner rounding."""
        t = int(min(w, h) * r * intensity * 0.09)
        if t <= 1:
            return
        alpha = _safe_alpha(r * intensity, 230)
        c = _with_alpha(color, alpha)

        path = QPainterPath()
        path.addRect(0, 0, w, h)  # outer edge: square, follows the screen
        path.addRoundedRect(t, t, w - 2 * t, h - 2 * t, t * 0.6, t * 0.6)
        path.setFillRule(Qt.FillRule.OddEvenFill)
        painter.fillPath(path, c)

    def _paint_full(self, painter, w, h, r, intensity, color):
        alpha = _safe_alpha(r * intensity, 190)
        if alpha <= 0:
            return
        gradient = QRadialGradient(QPointF(w / 2, h * 0.42), max(w, h) * 0.7)
        gradient.setColorAt(0.0, _with_alpha(color, int(alpha * 0.82)))
        gradient.setColorAt(1.0, _with_alpha(color, alpha))
        painter.fillRect(self.rect(), QBrush(gradient))

    def _text_font_for(self, r: float) -> QFont:
        """Cached QFont, rebuilt only when the point size changes."""
        size = int(30 + 14 * r)
        if self._text_font is None or self._text_font_size != size:
            font = QFont()
            font.setFamily("Microsoft YaHei")
            font.setPointSize(size)
            font.setBold(True)
            self._text_font = font
            self._text_font_size = size
        return self._text_font

    def _paint_text(self, painter, w, h, r):
        """Standalone text at one of 9 screen-edge-anchored positions."""
        if r <= 0.2:
            return
        alpha = _safe_alpha(r, 300)
        color = self._color()
        painter.setPen(_with_alpha(color, alpha))
        painter.setFont(self._text_font_for(r))

        text = self._config.overlay_text_content
        pos = self._config.overlay_text_position
        x, y, tw, th = _cell_rect(pos, w, h, 60)
        painter.drawText(x, y, tw, th, _TEXT_ALIGN.get(pos, _TEXT_ALIGN["cc"]), text)


class BlurOverlay(QObject):
    """Manages DimScreen windows across all monitors."""

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._screens: dict[str, tuple[DimScreen, object]] = {}  # name -> (win, screen)
        self._current_ratio = 0.0
        self._away = False
        self._create_all()

        app = QApplication.instance()
        if app:
            app.screenAdded.connect(self._on_screens_changed)
            app.screenRemoved.connect(self._on_screens_changed)

    def _create_all(self):
        app = QApplication.instance()
        if not app:
            return
        for screen in app.screens():
            self._create_for_screen(screen)

    def _create_for_screen(self, screen):
        name = screen.name()
        # Same-name reconnect (monitor re-plugged after resolution change):
        # replace the stale window instead of keeping the old geometry
        if name in self._screens:
            self._remove_screen_by_name(name)
        win = DimScreen(screen.geometry(), self._config)
        win.set_dim_ratio(self._current_ratio)
        win.set_away(self._away)
        # Follow resolution / DPI / rotation changes of this monitor
        screen.geometryChanged.connect(lambda geo, w=win: w.setGeometry(geo))
        self._screens[name] = (win, screen)

    def _remove_screen_by_name(self, name: str):
        if name not in self._screens:
            return
        win, screen = self._screens.pop(name)
        # Detach before deleteLater so a late geometryChanged can't hit a
        # deleted C++ widget
        try:
            screen.geometryChanged.disconnect()
        except TypeError:
            pass
        win.close()
        win.deleteLater()

    def _on_screens_changed(self, screen=None):
        app = QApplication.instance()
        if not app:
            return
        current_names = {s.name() for s in app.screens()}
        for name in list(self._screens):
            if name not in current_names:
                self._remove_screen_by_name(name)
        for s in app.screens():
            self._create_for_screen(s)
        self.refresh()

    def set_blur_ratio(self, ratio: float):
        if math.isnan(ratio):
            ratio = 0.0
        ratio = max(0.0, min(1.0, ratio))
        if ratio == self._current_ratio:
            return
        self._current_ratio = ratio
        for win, _ in self._screens.values():
            win.set_dim_ratio(ratio)

    def set_away(self, active: bool):
        self._away = active
        for win, _ in self._screens.values():
            win.set_away(active)

    def refresh(self):
        """Re-apply style/config changes and force a repaint on all windows."""
        for win, _ in self._screens.values():
            win._update_native_style()
            win.set_dim_ratio(self._current_ratio)
            win.set_away(self._away)
            # Style/text toggles can change the show/hide rule itself
            # (e.g. style "none" + text off must hide the window) — the
            # single visibility predicate decides, and it repaints when shown
            win._sync_visibility()

    def flash_away(self, duration_ms: int):
        """Preview the away dim on all monitors without changing real state."""
        for win, _ in self._screens.values():
            win.flash_away(duration_ms)

    def close_all(self):
        for name in list(self._screens):
            self._remove_screen_by_name(name)
