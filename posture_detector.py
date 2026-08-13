"""Posture detection using MediaPipe Pose and OpenCV webcam capture.

Baseline is stored in normalized nose-y coordinates (0.0-1.0 fraction of
frame height) so it survives camera resolution changes.
"""

import math
import threading
import time

import cv2
import mediapipe as mp
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from calibration import Calibration
from config import AppConfig

# Serializes all camera open/probe access — the detection worker and the
# UI's camera enumeration must never touch DSHOW concurrently.
camera_lock = threading.Lock()


class PostureDetector(QObject):
    """Runs webcam capture + MediaPipe pose detection on a background thread."""

    blur_ratio_changed = pyqtSignal(float)
    status_changed = pyqtSignal(str)
    frame_ready = pyqtSignal(np.ndarray)
    away_changed = pyqtSignal(bool)
    calibration_changed = pyqtSignal(bool)
    detection_stopped = pyqtSignal()  # worker loop exited for any reason

    MIN_CALIBRATION_VISIBILITY = 0.7
    CALIBRATION_WARMUP_FRAMES = 10
    AWAY_BLUR_SECONDS = 3.0
    MIN_STEADY_VISIBILITY = 0.4
    PREVIEW_FRAME_INTERVAL = 3  # emit every 3rd camera frame (~10 fps)

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._calibration = Calibration()

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._cap: cv2.VideoCapture | None = None
        self._stuck_thread: threading.Thread | None = None

        self._has_saved_calibration = self._config.calibration_saved
        if self._has_saved_calibration:
            self._calibration.calibrate(self._config.baseline_nose_y)

        self._warmup_count = 0
        self._last_ratio = -1.0
        self._last_away = False
        self._last_status = None  # dedupe repeated status messages
        self._preview_enabled = False

        self._slouch_start: float | None = None
        self._away_start: float | None = None

        # Time-based config snapshot (1 Hz) — staleness constant across fps
        self._cfg_cache: dict = {}
        self._cfg_last_refresh = 0.0
        self._preview_frame_idx = 0

    # ---- public API ----

    @property
    def preview_enabled(self) -> bool:
        return self._preview_enabled

    @preview_enabled.setter
    def preview_enabled(self, value: bool):
        self._preview_enabled = value
        if not value:
            self.frame_ready.emit(np.zeros((1, 1, 3), dtype=np.uint8))

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_calibrated(self) -> bool:
        return self._calibration.is_calibrated

    def start(self):
        if self.is_running:
            return
        if self._stuck_thread is not None:
            if not self._stuck_thread.is_alive():
                self._stuck_thread = None  # it exited on its own — recover
            else:
                # Give the blocked thread one more short window to unblock
                # (e.g. the device was just released) before refusing
                self._stuck_thread.join(timeout=2.0)
                if self._stuck_thread.is_alive():
                    self._emit_status("摄像头响应超时，无法重启。请检查设备后重启程序")
                    return
                self._stuck_thread = None
        self._stop_event.clear()
        self._warmup_count = 0
        self._last_ratio = -1.0
        self._last_away = False
        self._slouch_start = None
        self._away_start = None
        self._cfg_cache = {}
        self._cfg_last_refresh = 0.0
        self._thread = threading.Thread(target=self._detection_loop, daemon=True)
        self._thread.start()

        if self._has_saved_calibration:
            self._emit_status("已加载保存的校准标准，监测中...")
            self.calibration_changed.emit(True)
        else:
            self._emit_status("请坐直，正在自动校准...")
            self.calibration_changed.emit(False)

    def stop(self):
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
            if thread.is_alive():
                # Thread stuck in a blocking read — keep the reference so
                # start() refuses to spawn a second concurrent loop
                self._stuck_thread = thread
        self._thread = None
        self._slouch_start = None
        self._away_start = None
        self._set_away(False)
        self._emit_ratio(0.0)
        self._emit_status("已停止")

    def recalibrate(self):
        self._calibration.reset()
        self._has_saved_calibration = False
        # Drop the persisted baseline: a quit before the new warmup completes
        # must NOT silently restore the old calibration on next launch
        self._config.baseline_nose_y = 0.0
        self._warmup_count = 0
        self._slouch_start = None
        self._away_start = None
        self._set_away(False)
        self._emit_ratio(0.0)
        self.calibration_changed.emit(False)
        self._emit_status("请坐直，正在重新校准...")

    # ---- internal ----

    def _emit_status(self, text: str):
        if text != self._last_status:
            self._last_status = text
            self.status_changed.emit(text)

    def _snapshot_config(self, now: float) -> dict:
        """Time-based (1 Hz) snapshot of hot-path config values."""
        if not self._cfg_cache or now - self._cfg_last_refresh >= 1.0:
            c = self._config
            self._cfg_cache = {
                "sens": c.sens_multiplier,
                "dead": c.dead_zone_pct,
                "delay": c.delay_seconds,
                "blur_when_away": c.blur_when_away,
            }
            self._cfg_last_refresh = now
        return self._cfg_cache

    def _emit_ratio(self, ratio: float):
        if math.isnan(ratio):
            ratio = 0.0
        ratio = max(0.0, min(1.0, ratio))
        if ratio != self._last_ratio:
            self._last_ratio = ratio
            self.blur_ratio_changed.emit(ratio)

    def _set_away(self, active: bool):
        if active != self._last_away:
            self._last_away = active
            self.away_changed.emit(active)

    def _handle_away(self, now: float, cfg: dict):
        """Single away state machine: latch after 3 s without a clearly
        visible person; clear the timer when the option is disabled."""
        if cfg["blur_when_away"]:
            if self._away_start is None:
                self._away_start = now
                self._set_away(False)
            elif now - self._away_start >= self.AWAY_BLUR_SECONDS:
                self._set_away(True)
        else:
            self._set_away(False)
            self._away_start = None

    def _maybe_emit_preview(self, frame):
        if not self._preview_enabled:
            return
        self._preview_frame_idx += 1
        if self._preview_frame_idx % self.PREVIEW_FRAME_INTERVAL == 0:
            self.frame_ready.emit(frame)

    def _open_camera(self) -> cv2.VideoCapture | None:
        idx = self._config.camera_index
        with camera_lock:
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if not cap.isOpened():
                if idx != 0:
                    cap.release()
                cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                self._emit_status("未检测到摄像头")
                return None
            # Virtual cameras may reject property sets — keep driver defaults
            for prop, value in (
                (cv2.CAP_PROP_FRAME_WIDTH, 640),
                (cv2.CAP_PROP_FRAME_HEIGHT, 480),
                (cv2.CAP_PROP_FPS, 30),
            ):
                try:
                    cap.set(prop, value)
                except cv2.error:
                    pass
            return cap

    def _detection_loop(self):
        cap = None
        pose = None
        try:
            cap = self._open_camera()
            if cap is None:
                return  # falls through to finally → detection_stopped fires
            self._cap = cap

            fps_target = self._config.detect_fps
            interval = max(1, round(30 / fps_target))

            pose = mp.solutions.pose.Pose(
                static_image_mode=False,
                model_complexity=1,
                smooth_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )

            frame_idx = 0


            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue

                frame = cv2.flip(frame, 1)

                # Frame-skip to the configured detection frequency;
                # skipped frames hold the previous judgment
                frame_idx += 1
                if interval > 1 and frame_idx % interval != 0:
                    self._maybe_emit_preview(frame)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                results = pose.process(rgb)

                now = time.monotonic()
                cfg = self._snapshot_config(now)
                ratio = 0.0

                if results.pose_landmarks:
                    nose = results.pose_landmarks.landmark[0]
                    nose_y_norm = nose.y  # already normalized 0.0-1.0
                    visibility = nose.visibility if hasattr(nose, 'visibility') else 1.0

                    if self._preview_enabled:
                        mp.solutions.drawing_utils.draw_landmarks(
                            frame, results.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS,
                            mp.solutions.drawing_utils.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
                            mp.solutions.drawing_utils.DrawingSpec(color=(255, 255, 255), thickness=1),
                        )

                    # Not clearly visible (e.g. a stray arm): the away machine
                    # still runs, so a half-visible person gets away protection
                    if visibility < self.MIN_STEADY_VISIBILITY:
                        self._handle_away(now, cfg)
                        self._maybe_emit_preview(frame)
                        continue

                    # Person clearly visible → clear away state
                    self._set_away(False)
                    self._away_start = None

                    # Auto-calibrate (first run or after recalibrate)
                    if not self._calibration.is_calibrated:
                        if visibility >= self.MIN_CALIBRATION_VISIBILITY and not math.isnan(nose_y_norm):
                            self._warmup_count += 1
                            if self._warmup_count == 1:
                                self._emit_status("请坐直，正在自动校准...")
                            if self._warmup_count >= self.CALIBRATION_WARMUP_FRAMES:
                                self._calibration.calibrate(nose_y_norm)
                                self._config.baseline_nose_y = nose_y_norm
                                self._has_saved_calibration = True
                                self.calibration_changed.emit(True)
                                self._emit_status("校准完成！已保存为标准坐姿，监测中...")
                        else:
                            self._warmup_count = 0
                            self._emit_status("未检测到清晰人脸，请正对摄像头...")
                        self._emit_ratio(0.0)
                        self._maybe_emit_preview(frame)
                        continue

                    # Compute slouch ratio with delay
                    if not math.isnan(nose_y_norm):
                        raw_ratio = self._calibration.deviation_ratio(
                            nose_y_norm, cfg["sens"], cfg["dead"],
                        )
                        ratio = self._apply_delay(raw_ratio, now, cfg["delay"])
                else:
                    # No landmarks at all
                    self._handle_away(now, cfg)
                    self._slouch_start = None
                    ratio = 0.0

                self._emit_ratio(ratio)
                self._maybe_emit_preview(frame)

        except Exception as e:
            self._emit_status(f"检测异常：{e}")
        finally:
            if cap is not None:
                cap.release()
            self._cap = None
            if pose is not None:
                pose.close()
            self.detection_stopped.emit()

    def _apply_delay(self, raw_ratio: float, now: float, delay: float) -> float:
        """Configurable delay before blur activates."""
        if raw_ratio <= 0.001:
            self._slouch_start = None
            return 0.0
        if self._slouch_start is None:
            self._slouch_start = now
        return raw_ratio if now - self._slouch_start >= delay else 0.0
