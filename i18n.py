"""Minimal zh/en translation layer.

The codebase uses Chinese literals as the canonical strings; when the
language is "en", translate() maps them to English. Unknown strings pass
through unchanged, so status messages from the detector always render.
"""

_EN = {
    # ---- window ----
    "WinDorso – 坐姿监测": "WinDorso – Posture Monitor",

    # ---- monitor area ----
    "摄像头画面": "Camera Preview",
    "低头程度": "Slouch Level",
    "停止监测": "Stop Monitoring",
    "开始监测": "Start Monitoring",
    "快捷键": "Hotkey",
    "就绪": "Ready",
    "正在搜索摄像头...": "Searching for cameras...",

    # ---- calibration card ----
    "校准": "Calibration",
    "摄像头": "Camera",
    "校准状态": "Calibration Status",
    "● 已校准": "● Calibrated",
    "● 未校准": "● Not calibrated",
    "重新校准": "Recalibrate",
    "搜索中...": "Searching...",
    "摄像头 {n}": "Camera {n}",
    "点击下拉选择，滚轮不会误改": "Click to select; the wheel never changes it",

    # ---- detection card ----
    "检测设置": "Detection",
    "灵敏度": "Sensitivity",
    "容忍度": "Tolerance",
    "延迟(秒)": "Delay (s)",
    "检测频率": "Detection FPS",
    "{v}帧/秒": "{v} fps",
    "频率越高反应越快，CPU 占用越高；松手后生效":
        "Higher FPS reacts faster but uses more CPU; applied on release",
    "灵敏度：越高，低头越容易触发提醒\n容忍度：允许轻微低头不提醒的范围，数值越高越宽松\n延迟：低头持续该时长后才触发提醒\n检测频率：每秒判断姿态的次数，越高反应越快":
        "Sensitivity: higher makes slouching trigger sooner\n"
        "Tolerance: how much slight lowering is ignored; higher is more lenient\n"
        "Delay: how long the slouch must persist before the warning\n"
        "Detection FPS: posture judgments per second; higher reacts faster",

    # ---- warning style ----
    "警告样式": "Warning Style",
    "模糊": "Blur",
    "光晕": "Glow",
    "边框": "Border",
    "全屏": "Fullscreen",
    "无": "None",
    "文字（可叠加）": "Text (stackable)",
    "在所选样式上叠加文字提醒": "Stack a text reminder on the selected style",

    # ---- color card ----
    "颜色": "Color",
    "黑色": "Black",
    "白色": "White",
    "红色": "Red",
    "橙色": "Orange",
    "黄色": "Yellow",
    "绿色": "Green",
    "蓝色": "Blue",
    "紫色": "Purple",
    "自定义颜色...": "Custom Color...",
    "当前：{name}": "Current: {name}",
    "选择警告颜色": "Choose Warning Color",

    # ---- text reminder ----
    "文字提醒设置": "Text Reminder Settings",
    "文字": "Text",
    "输入提醒文字": "Enter reminder text",
    "位置": "Position",
    "左上": "Top Left", "上中": "Top Center", "右上": "Top Right",
    "左中": "Middle Left", "居中": "Center", "右中": "Middle Right",
    "左下": "Bottom Left", "下中": "Bottom Center", "右下": "Bottom Right",

    # ---- intensity ----
    "强度": "Intensity",
    "覆盖强度": "Overlay Strength",

    # ---- options ----
    "选项": "Options",
    "低头时锁定鼠标（严格模式）": "Lock mouse while slouching (strict mode)",
    "离开摄像头时自动模糊屏幕": "Dim screen when away from camera",
    "离开模糊强度": "Away Dim Strength",
    "按住拖动实时预览效果，松手后自动消失":
        "Hold and drag to preview; fades out on release",
    "开机自启": "Launch at Login",

    # ---- general ----
    "通用": "General",
    "暗色模式": "Dark Mode",
    "语言": "Language",

    # ---- hotkey ----
    "点击后按下新的组合键，Esc 取消": "Click, then press a new combo; Esc to cancel",
    "注册失败：快捷键可能被其他程序占用":
        "Registration failed: the combo may be taken by another app",
    "⚠ 不支持小键盘按键，请使用主键盘字母/数字/F1-F12":
        "⚠ Numpad keys are not supported — use letters/digits/F1-F12 on the main keyboard",
    "⚠ 快捷键仅支持字母/数字/F1-F12":
        "⚠ Hotkey supports letters/digits/F1-F12 only",
    "⚠ 快捷键需包含 Ctrl/Alt/Shift/Win":
        "⚠ The hotkey must include Ctrl/Alt/Shift/Win",
    "快捷键已更新为 {hk}": "Hotkey updated to {hk}",
    "⚠ 快捷键注册失败，已恢复原快捷键":
        "⚠ Registration failed — the previous hotkey was restored",
    "已取消快捷键修改": "Hotkey change cancelled",
    "(点击后按下组合键：Ctrl/Alt/Shift/Win + 字母/数字/F1-F12，Esc 取消)":
        "(Click, then press a combo: Ctrl/Alt/Shift/Win + letter/digit/F1-F12, Esc to cancel)",

    # ---- calibration hint dialog ----
    "首次使用": "First Launch",
    "请保持正确坐姿，程序将自动完成校准。\n校准完成后会保存为标准，以后每次启动都自动使用。\n如需更换标准，点击「重新校准」。":
        "Sit with correct posture; calibration runs automatically.\n"
        "The result is saved and reused on every launch.\n"
        "Click “Recalibrate” to set a new baseline.",

    # ---- single-instance dialog ----
    "程序已在运行中，请勿重复启动": "The app is already running — please don't launch it twice",

    # ---- detector status messages (Chinese literals) ----
    "已加载保存的校准标准，监测中...": "Loaded saved calibration, monitoring...",
    "请坐直，正在自动校准...": "Sit upright — calibrating...",
    "请坐直，正在重新校准...": "Sit upright — recalibrating...",
    "校准完成！已保存为标准坐姿，监测中...":
        "Calibration complete! Saved as the baseline, monitoring...",
    "未检测到清晰人脸，请正对摄像头...": "No clear face — please face the camera...",
    "未检测到摄像头": "No camera found",
    "已停止": "Stopped",
    "摄像头响应超时，无法重启。请检查设备后重启程序":
        "Camera timeout — cannot restart. Check the device and relaunch the app",
}

# Prefix-based translation for dynamic messages
_DETECT_ERROR_PREFIX_ZH = "检测异常："
_DETECT_ERROR_PREFIX_EN = "Detection error: "


def translate(text: str, lang: str) -> str:
    """Translate a Chinese-literal string to the target language.

    "zh" returns the text unchanged; "en" looks it up in the dictionary.
    Unknown strings pass through.
    """
    if lang == "zh" or not text:
        return text

    if text in _EN:
        return _EN[text]

    if text.startswith(_DETECT_ERROR_PREFIX_ZH):
        return _DETECT_ERROR_PREFIX_EN + text[len(_DETECT_ERROR_PREFIX_ZH):]

    return text
