"""Application configuration persisted via QSettings.

Thread safety: one QSettings instance is shared between the GUI thread
(writes on slider/checkbox changes) and the detection worker (reads).
All access goes through _get/_set guarded by a lock.
"""

import threading
from PyQt6.QtCore import QSettings

SETTINGS_ORG = "WinDorso"
SETTINGS_APP = "WinDorso"

# Single source of truth for warning styles (key -> display label).
# Text reminder is NOT a style — it is a separate layer that can be
# combined with any style (config.overlay_text_enabled).
STYLE_LABELS = {
    "blur": "模糊",
    "glow": "光晕",
    "border": "边框",
    "fullscreen": "全屏",
    "none": "无",
}


def _safe_int(value, default):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value, default):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_bool(value, default):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    if value is None:
        return default
    return bool(value)


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


class AppConfig:
    def __init__(self):
        self._settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self._lock = threading.Lock()
        self._migrate_v2()

    def _migrate_v2(self):
        """One-time migration: text-style split-out only.

        Defaults for new keys are written ONLY when the key is absent, so
        pre-v2 users keep their customized values.
        """
        if _safe_bool(self._get("app/migrated_v2", False), False):
            return
        if not self._contains("detection/delay_tenths"):
            self._set("detection/delay_tenths", 3)   # 0.3 s
        if not self._contains("detection/fps"):
            self._set("detection/fps", 30)
        if not self._contains("detection/dead_zone"):
            self._set("detection/dead_zone", 1)
        # The former standalone "text" style becomes a combinable layer
        old_style = str(self._get("overlay/warning_style", "") or "")
        if old_style == "text":
            self._set("overlay/warning_style", "none")
            self._set("overlay/text_enabled", True)
        self._set("app/migrated_v2", True)

    def _get(self, key, default):
        with self._lock:
            return self._settings.value(key, default)

    def _set(self, key, value):
        with self._lock:
            self._settings.setValue(key, value)

    def _contains(self, key) -> bool:
        with self._lock:
            return self._settings.contains(key)

    # ---- calibration (normalized nose y, 0.0-1.0 fraction of frame height) ----
    @property
    def baseline_nose_y(self) -> float:
        v = _safe_float(self._get("calibration/baseline_nose_y", 0.0), 0.0)
        return _clamp(v, 0.0, 1.0)

    @baseline_nose_y.setter
    def baseline_nose_y(self, value: float):
        v = _clamp(value, 0.0, 1.0)
        self._set("calibration/baseline_nose_y", float(v))

    @property
    def calibration_saved(self) -> bool:
        if not self._contains("calibration/baseline_nose_y"):
            return False
        v = _safe_float(self._get("calibration/baseline_nose_y", 0.0), 0.0)
        # Strictly positive: 0.0 (or unparseable garbage defaulting to 0.0)
        # must not be treated as a valid saved baseline
        return 0.0 < v < 1.0

    # ---- sensitivity 1-5 ----
    @property
    def sensitivity(self) -> int:
        return _clamp(_safe_int(self._get("detection/sensitivity", 3), 3), 1, 5)

    @sensitivity.setter
    def sensitivity(self, value: int):
        self._set("detection/sensitivity", _clamp(value, 1, 5))

    # ---- dead zone 1-5 (default 1) ----
    @property
    def dead_zone(self) -> int:
        return _clamp(_safe_int(self._get("detection/dead_zone", 1), 1), 1, 5)

    @dead_zone.setter
    def dead_zone(self, value: int):
        self._set("detection/dead_zone", _clamp(value, 1, 5))

    # ---- delay 0.0-1.0 s (stored as tenths, 0-10; default 0.3 s) ----
    @property
    def delay_tenths(self) -> int:
        return _clamp(_safe_int(self._get("detection/delay_tenths", 3), 3), 0, 10)

    @delay_tenths.setter
    def delay_tenths(self, value: int):
        self._set("detection/delay_tenths", _clamp(value, 0, 10))

    @property
    def delay_seconds(self) -> float:
        return self.delay_tenths / 10.0

    # ---- detection frequency (judgments per second, snapped to 5-step) ----
    @property
    def detect_fps(self) -> int:
        v = _safe_int(self._get("detection/fps", 30), 30)
        return max(5, min(30, int(round(v / 5.0) * 5)))

    @detect_fps.setter
    def detect_fps(self, value: int):
        self._set("detection/fps", max(5, min(30, int(round(value / 5.0) * 5))))

    # ---- derived ----
    @property
    def dead_zone_pct(self) -> float:
        return self.dead_zone * 0.02 - 0.01

    @property
    def sens_multiplier(self) -> float:
        return 0.4 + self.sensitivity * 0.2

    # ---- monitoring ----
    @property
    def monitoring_enabled(self) -> bool:
        return _safe_bool(self._get("detection/monitoring_enabled", True), True)

    @monitoring_enabled.setter
    def monitoring_enabled(self, value: bool):
        self._set("detection/monitoring_enabled", value)

    # ---- camera ----
    @property
    def camera_index(self) -> int:
        return _safe_int(self._get("detection/camera_index", 0), 0)

    @camera_index.setter
    def camera_index(self, value: int):
        self._set("detection/camera_index", int(value))

    # ---- warning style ----
    VALID_STYLES = tuple(STYLE_LABELS.keys())

    @property
    def warning_style(self) -> str:
        val = str(self._get("overlay/warning_style", "blur"))
        return val if val in self.VALID_STYLES else "blur"

    @warning_style.setter
    def warning_style(self, value: str):
        if value in self.VALID_STYLES:
            self._set("overlay/warning_style", value)

    # ---- overlay color (hex string) ----
    @property
    def overlay_color(self) -> str:
        val = self._get("overlay/color", "#C82020")
        s = str(val) if val else "#C82020"
        if len(s) == 7 and s[0] == "#":
            try:
                int(s[1:], 16)
                return s
            except ValueError:
                pass
        return "#C82020"

    @overlay_color.setter
    def overlay_color(self, value: str):
        self._set("overlay/color", value)

    # ---- overlay text layer (combinable with any style) ----
    @property
    def overlay_text_enabled(self) -> bool:
        return _safe_bool(self._get("overlay/text_enabled", False), False)

    @overlay_text_enabled.setter
    def overlay_text_enabled(self, value: bool):
        self._set("overlay/text_enabled", value)

    @property
    def overlay_text_content(self) -> str:
        val = self._get("overlay/text_content", "请坐直！")
        return str(val) if val else "请坐直！"

    @overlay_text_content.setter
    def overlay_text_content(self, value: str):
        self._set("overlay/text_content", value)

    @property
    def overlay_text_position(self) -> str:
        valid = ("tl", "tc", "tr", "cl", "cc", "cr", "bl", "bc", "br")
        val = str(self._get("overlay/text_position", "cc"))
        return val if val in valid else "cc"

    @overlay_text_position.setter
    def overlay_text_position(self, value: str):
        self._set("overlay/text_position", value)

    # ---- intensity 1-10 ----
    @property
    def overlay_intensity(self) -> int:
        return _clamp(_safe_int(self._get("overlay/intensity", 5), 5), 1, 10)

    @overlay_intensity.setter
    def overlay_intensity(self, value: int):
        self._set("overlay/intensity", _clamp(value, 1, 10))

    @property
    def intensity_normalized(self) -> float:
        return self.overlay_intensity / 10.0

    # ---- block mouse ----
    @property
    def overlay_block_mouse(self) -> bool:
        return _safe_bool(self._get("overlay/block_mouse", False), False)

    @overlay_block_mouse.setter
    def overlay_block_mouse(self, value: bool):
        self._set("overlay/block_mouse", value)

    # ---- blur when away ----
    @property
    def blur_when_away(self) -> bool:
        return _safe_bool(self._get("overlay/blur_when_away", False), False)

    @blur_when_away.setter
    def blur_when_away(self, value: bool):
        self._set("overlay/blur_when_away", value)

    # ---- away intensity 1-10 ----
    @property
    def away_intensity(self) -> int:
        return _clamp(_safe_int(self._get("overlay/away_intensity", 7), 7), 1, 10)

    @away_intensity.setter
    def away_intensity(self, value: int):
        self._set("overlay/away_intensity", _clamp(value, 1, 10))

    @property
    def away_intensity_normalized(self) -> float:
        return self.away_intensity / 10.0

    # ---- camera preview visibility ----
    @property
    def show_camera_preview(self) -> bool:
        return _safe_bool(self._get("ui/show_camera_preview", True), True)

    @show_camera_preview.setter
    def show_camera_preview(self, value: bool):
        self._set("ui/show_camera_preview", value)

    # ---- launch at login ----
    @property
    def launch_at_login(self) -> bool:
        return _safe_bool(self._get("app/launch_at_login", False), False)

    @launch_at_login.setter
    def launch_at_login(self, value: bool):
        self._set("app/launch_at_login", value)

    # ---- theme: "dark" | "light" ----
    @property
    def theme(self) -> str:
        val = str(self._get("app/theme", "dark"))
        return val if val in ("dark", "light") else "dark"

    @theme.setter
    def theme(self, value: str):
        if value in ("dark", "light"):
            self._set("app/theme", value)

    # ---- language: "zh" | "en" ----
    @property
    def language(self) -> str:
        val = str(self._get("app/language", "zh"))
        return val if val in ("zh", "en") else "zh"

    @language.setter
    def language(self, value: str):
        if value in ("zh", "en"):
            self._set("app/language", value)

    # ---- persisted window size (0 = not saved yet) ----
    @property
    def window_width(self) -> int:
        return _safe_int(self._get("app/window_width", 0), 0)

    @window_width.setter
    def window_width(self, value: int):
        self._set("app/window_width", int(value))

    @property
    def window_height(self) -> int:
        return _safe_int(self._get("app/window_height", 0), 0)

    @window_height.setter
    def window_height(self, value: int):
        self._set("app/window_height", int(value))

    # ---- global hotkey (Win32 modifiers | virtual key) ----
    @property
    def hotkey_modifiers(self) -> int:
        return _safe_int(self._get("hotkey/modifiers", 0x0003), 0x0003)  # Ctrl+Alt

    @hotkey_modifiers.setter
    def hotkey_modifiers(self, value: int):
        self._set("hotkey/modifiers", int(value))

    @property
    def hotkey_key(self) -> int:
        return _safe_int(self._get("hotkey/key", 0x44), 0x44)  # VK_D

    @hotkey_key.setter
    def hotkey_key(self, value: int):
        self._set("hotkey/key", int(value))
