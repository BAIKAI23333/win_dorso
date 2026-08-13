# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

WinDorso — [tldev/dorso](https://github.com/tldev/dorso)（macOS 坐姿监测应用）的 Windows 移植版。摄像头 + MediaPipe Pose 实时检测坐姿，低头时在屏幕上叠加视觉警告（模糊/光晕/边框/全屏 + 可叠加文字提醒）。全部处理在本机完成，画面不出进程。技术栈：Python 3.11+、PyQt6、MediaPipe、OpenCV，仅支持 Windows（大量 Win32 ctypes 调用）。

功能与使用文档见 [README.md](README.md)（英文，权威）；中文版为 READEME.zh.md（文件名拼写如此，勿"修正"）。

## 常用命令

```powershell
# 环境：推荐 venv（项目开发环境为 conda env win_dorso, Python 3.11）
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt   # 完整 pip list 快照

# 运行（仅允许单实例）
python main.py
```

- [requirements.txt](requirements.txt) 是测试环境的完整 `pip list` 快照；[pyproject.toml](pyproject.toml) 含顶层依赖（`pip install .` 亦可）。
- 无测试、无 linter 配置。改动后手动运行 `python main.py` 验证（需摄像头）。
- 新增顶层 .py 模块时，同步加入 pyproject.toml 的 `[tool.setuptools] py-modules` 列表。

## 架构

### 线程模型（核心）

两条线程，通过 Qt 信号通信：

- **GUI 线程**：`MainWindow`（[main_window.py](main_window.py)）、`BlurOverlay`（[blur_overlay.py](blur_overlay.py)）
- **检测线程**：[posture_detector.py](posture_detector.py) 的 `PostureDetector` 是挂在 GUI 线程的 QObject，其 `_detection_loop` 跑在 daemon `threading.Thread` 上；通过 `blur_ratio_changed` / `status_changed` / `frame_ready` / `away_changed` / `calibration_changed` / `detection_stopped` 信号回传（跨线程 queued connection）。
- `posture_detector.camera_lock` 串行化所有 DSHOW 摄像头打开/枚举：启动时序保证摄像头枚举先于检测启动（4 秒兜底定时器，见 `MainWindow.__init__` 的 `_probe_done` / `_startup_timer`），避免两个消费者争抢同一设备（虚拟摄像头尤甚）。

### 配置（config.py）

`AppConfig` 基于 QSettings（Windows 注册表）持久化，线程安全（锁保护 `_get`/`_set`）：GUI 线程在控件变更时写，检测线程读。热路径值由 worker 以 1 Hz 快照缓存（`_snapshot_config`），保证延迟常数与 FPS 无关。

- 新增设置 = 在 AppConfig 上加一对 property（带 clamp/safe parse，参考现有代码）。
- 旧用户迁移模式见 `_migrate_v2`：新 key 仅在缺失时写默认值，不覆盖已有自定义值。

### 校准与判定（calibration.py）

- 基线为**归一化鼻子 Y 坐标**（0–1，帧高比例），因此分辨率变化不影响已保存校准。
- `Calibration.deviation` 用 30 帧滑动窗口平滑；`deviation_ratio` 结合灵敏度乘数与死区输出 0–1 的低头比例。全模糊阈值 `FULL_BLUR_FRACTION = 0.25`。

### 覆盖层（blur_overlay.py）

- `BlurOverlay` 为每台显示器管理一个 `DimScreen`（全屏无边框置顶），监听屏幕增删/分辨率变化。
- 点击穿透靠原生 `WS_EX_TRANSPARENT`（严格模式下移除以捕获鼠标）。
- 显隐由唯一谓词 `_should_show()` 决定，避免不同路径显隐规则分歧；样式 blur/glow/border/fullscreen/none 在 `paintEvent` 中用 QPainter 绘制；文字提醒是与样式正交的可叠加层；"离开"状态是独立的中性暗色。

### 国际化（i18n.py）

**中文字面量是代码里的规范字符串**；`translate(text, lang)` 在 lang=="en" 时查 `_EN` 字典映射，未命中原样返回。新增 UI 字符串流程：① 代码里写中文字面量 → ② 在 [i18n.py](i18n.py) 的 `_EN` 加对应英文。动态错误消息走前缀替换（`检测异常：` → `Detection error: `）。

### 入口（main.py）

单实例互斥锁（`CreateMutexW`）、Qt 中文翻译加载、全局字体（Microsoft YaHei UI 11pt）。全局热键（默认 Ctrl+Alt+D）通过 `RegisterHotKey` + `QAbstractNativeEventFilter` 实现，见 main_window.py 的 `HotkeyFilter`。

## 约定

- **任何 UI 改动前必须先读 `.claude/skills/dorso-design/SKILL.md`**（Dorso 设计语言：brandCyan #4fd1c5、低透明度强调、11pt 行高 / 12pt 卡标题、复用 SettingsCard/BrandSwitch 等既有组件模式）。主题 token 集中在 main_window.py 的 `THEME_TOKENS`（dark/light）。
- 设置页的滑动条/下拉框必须用 `NoWheelSlider` / `NoWheelComboBox`（滚动设置页时滚轮不得改值）。
- 已知限制（设计取舍，勿当 bug 修）：Blur 样式只是半透明暗化近似——Windows 每像素 alpha 窗口拿不到真正背景模糊；小键盘键不能作为热键组合（映射为独立 VK 码）。
- `.claude/` 目录已被 gitignore，是个人 Claude Code 配置。
