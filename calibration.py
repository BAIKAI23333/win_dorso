"""Calibration logic – baseline recording and deviation calculation.

All values are normalized (0.0-1.0 fraction of frame height), so the stored
baseline survives camera resolution changes.

Thread safety: calibrate()/reset() may be called from the GUI thread while
deviation() runs in the worker thread. A threading.Lock guards all shared state.
"""

import math
import threading
from collections import deque
from dataclasses import dataclass, field

# Nose drop of 25% of frame height = full blur
FULL_BLUR_FRACTION = 0.25


@dataclass
class Calibration:
    """Holds the calibrated baseline and computes deviation (normalized)."""

    baseline_nose_y: float = 0.0
    _calibrated: bool = False

    _history: deque = field(default_factory=lambda: deque(maxlen=30))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def is_calibrated(self) -> bool:
        with self._lock:
            return self._calibrated

    def calibrate(self, nose_y: float):
        """Record the current normalized nose Y as the correct-posture baseline."""
        with self._lock:
            self.baseline_nose_y = nose_y
            self._calibrated = True
            self._history.clear()

    def reset(self):
        with self._lock:
            self._calibrated = False
            self.baseline_nose_y = 0.0
            self._history.clear()

    def deviation(self, nose_y: float) -> float:
        """Return the smoothed downward deviation of the nose from baseline.

        NaN-safe: skips NaN inputs and clamps extreme samples.
        """
        if math.isnan(nose_y):
            return 0.0

        with self._lock:
            if not self._calibrated:
                return 0.0

            raw = nose_y - self.baseline_nose_y
            # Symmetric clamp: extreme frames (head-up OR head-down spikes)
            # must not poison the 30-frame average. Down side capped at 0.5
            # (2x full-blur fraction) — anything beyond is a detection glitch.
            clamped = max(-self.baseline_nose_y, min(raw, 0.5))
            self._history.append(clamped)

            smoothed = sum(self._history) / len(self._history)

        if math.isnan(smoothed):
            return 0.0
        return max(0.0, smoothed)

    def deviation_ratio(
        self, nose_y: float, sensitivity: float, dead_zone_pct: float,
    ) -> float:
        """Return blur intensity as a 0.0–1.0 ratio (all normalized units)."""
        dev = self.deviation(nose_y)
        if dev <= 0 or math.isnan(dev):
            return 0.0

        if dev < dead_zone_pct:
            return 0.0

        effective = dev - dead_zone_pct
        return min(1.0, (effective * sensitivity) / FULL_BLUR_FRACTION)
