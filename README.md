# WinDorso

Mac has the Dorso project to protect people's cervical spine and neck, but Windows doesn't seem to have a similar open-source project, which is something I really don't want to see (qwq)

My English is pretty bad, and most of the English version of the readme is machine-translated, please forgive me.

A Windows port of [tldev/dorso](https://github.com/tldev/dorso) — a posture
monitor that watches you through the webcam and visually nudges you when you
slouch. All processing is local; no image ever leaves your machine.

When you slouch or bend down, the screen dims with a warning effect. Sit up
straight and it clears instantly.

## Features

- **Camera posture detection** — MediaPipe Pose (33 landmarks), real-time on CPU
- **Auto-calibration** — sit upright for a moment; the baseline is saved and
  reused on every launch (normalized coordinates survive resolution changes)
- **5 warning styles** — Blur, Glow, Border, Fullscreen, None
- **Stackable text reminder** — custom text, 9 screen-edge positions,
  combinable with any style
- **Custom colors** — 8 named swatches + full color picker
- **Configurable detection** — sensitivity, tolerance (dead zone),
  delay (0–1 s), detection FPS (5–30)
- **Away dim** — optionally dims the screen when you leave the camera,
  with its own adjustable strength and hold-to-preview feedback
- **Strict mode** — optionally locks mouse input while you slouch
- **Global hotkey** — toggle monitoring from anywhere (default `Ctrl+Alt+D`,
  fully customizable via click-to-record)
- **Dark / light themes**, **Chinese / English UI**
- **Resizable + fullscreen** (`F11`), size persisted across launches
- **Multi-monitor** overlays with resolution-change tracking
- **Anti-misclick** — mouse wheel never changes combo/slider values
- **Launch at login** (Windows registry)

## Requirements

- Windows 10/11
- A webcam
- Python 3.11+ ([python.org](https://www.python.org/downloads/) or the
  Microsoft Store)

> **Development environment:** this project was developed in a Miniconda
> virtual environment (`conda env win_dorso`, Python 3.11). The instructions
> below use the standard `venv` so that anyone can run it without conda —
> conda is provided as an alternative.

## Installation

With the standard `venv` (recommended):

```powershell
cd path\to\win_dorso
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Or with conda, if you already use it:

```powershell
conda create -n win_dorso python=3.11
conda activate win_dorso
pip install -r requirements.txt
```

> `requirements.txt` is a full `pip list` snapshot of the tested environment.
> A `pyproject.toml` with the top-level dependencies is also provided
> (`pip install .` works).

## Run

```powershell
# venv
.venv\Scripts\activate
python main.py

# or conda
conda activate win_dorso
python main.py
```

On first launch the app asks you to sit with correct posture; calibration
runs automatically and is saved. The camera preview auto-hides on subsequent
launches once a calibration exists.

## Usage

| Control | What it does |
|---|---|
| **Start/Stop Monitoring** | manual toggle (also the global hotkey) |
| **Recalibrate** | expand the camera view and re-record the baseline |
| **Sensitivity** | higher = slouching triggers sooner |
| **Tolerance** | how much slight lowering is ignored; higher is more lenient |
| **Delay** | 0–1 s; how long the slouch must persist before the warning |
| **Detection FPS** | posture judgments per second (applied on release) |
| **Warning Style** | Blur / Glow / Border / Fullscreen / None |
| **Text (stackable)** | overlay custom text at one of 9 screen positions |
| **Color** | 8 named swatches or a custom color |
| **Overlay Strength** | 1–10 intensity of the visual effect |
| **Lock mouse while slouching** | strict mode; the overlay captures clicks until you sit up |
| **Dim screen when away** | after ~3 s without a clear face, dim the screen |
| **Away Dim Strength** | hold-and-drag for a live preview |
| **Launch at Login** | registry Run entry |
| **Dark Mode** | dark/light theme |
| **Language** | 中文 / English |
| **Hotkey** | click to record a new combo (Esc cancels) |

## Project layout

```
win_dorso/
├── main.py              # entry point (single-instance guard, Qt translations)
├── main_window.py       # settings window (theme/i18n/responsive layout)
├── posture_detector.py  # MediaPipe detection worker (threaded)
├── blur_overlay.py      # per-monitor overlay windows (styles + text layer)
├── calibration.py       # normalized baseline + smoothed deviation
├── config.py            # QSettings-backed, thread-safe configuration
├── i18n.py              # zh/en translation layer
├── pyproject.toml       # project metadata + top-level dependencies
└── requirements.txt     # pip snapshot
```

## Design notes

- All processing is **local** — frames never leave the process.
- Overlay windows are click-through (`WS_EX_TRANSPARENT`) unless strict mode
  is enabled; then they capture clicks on purpose.
- Camera enumeration completes **before** detection starts (4 s fallback) so
  DSHOW devices are never opened by two consumers at once — important for
  virtual cameras.
- Configuration is stored in the registry via QSettings and guarded by a
  lock (worker thread reads, GUI thread writes).

## Known limitations

- The "Blur" style is a translucent dim approximation; true backdrop blur of
  other windows is not available to per-pixel-alpha windows on Windows.
- Numpad keys cannot be recorded as hotkey combos (they map to distinct VK
  codes).
- Only one instance may run at a time (enforced by a mutex).
