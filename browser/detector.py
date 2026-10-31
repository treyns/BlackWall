"""Auto-pause detection: fullscreen apps, idle desktop, battery power.

Pure Win32 helpers - the wallpaper engine polls this with its own timer.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass, field

from core.models import MonitorInfo

GWL_STYLE = -16
WS_CAPTION = 0x00C00000
MONITOR_DEFAULTTONEAREST = 2
SMTO_ABORTIFHUNG = 0x0002

SHELL_CLASSES = {
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow", "ApplicationFrameWindow",
}


class _RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class _SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


@dataclass
class PauseState:
    fullscreen_monitors: set[str] = field(default_factory=set)
    idle: bool = False
    idle_seconds: float = 0.0
    on_battery: bool = False


def _class_name(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def _foreground_fullscreen() -> tuple[int, _RECT] | None:
    if not hasattr(ctypes, "windll"):
        return None
    user32 = ctypes.windll.user32
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return None
        if not user32.IsWindowVisible(hwnd):
            return None
        if _class_name(hwnd) in SHELL_CLASSES:
            return None
        rect = _RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if rect.right - rect.left <= 0 or rect.bottom - rect.top <= 0:
            return None
        return hwnd, rect
    except Exception:  # noqa: BLE001
        return None


def _idle_seconds() -> float:
    if not hasattr(ctypes, "windll"):
        return 0.0
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        millis = ctypes.windll.kernel32.GetTickCount() - info.dwTime
        return max(0.0, millis / 1000.0)
    except Exception:  # noqa: BLE001
        return 0.0


def on_battery_power() -> bool:
    if not hasattr(ctypes, "windll"):
        return False
    try:
        status = _SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return status.ACLineStatus == 0 and status.BatteryLifePercent != 255
    except Exception:  # noqa: BLE001
        pass
    return False


class AutoPauseDetector:
    def __init__(self, settings) -> None:
        self.settings = settings

    def poll(self, monitors: list[MonitorInfo]) -> PauseState:
        state = PauseState()
        idle_limit = float(self.settings.get("performance.idle_minutes", 5) or 5) * 60.0
        if self.settings.get("performance.pause_when_idle", True):
            state.idle_seconds = _idle_seconds()
            state.idle = state.idle_seconds >= idle_limit
        state.on_battery = on_battery_power()

        if self.settings.get("performance.pause_on_fullscreen", True):
            found = _foreground_fullscreen()
            if found is not None:
                _hwnd, rect = found
                for monitor in monitors:
                    left = monitor.x
                    top = monitor.y
                    right = left + monitor.width
                    bottom = top + monitor.height
                    overlap_w = max(0, min(rect.right, right) - max(rect.left, left))
                    overlap_h = max(0, min(rect.bottom, bottom) - max(rect.top, top))
                    coverage = (overlap_w * overlap_h) / max(1.0, monitor.width * monitor.height)
                    if coverage >= 0.94:
                        state.fullscreen_monitors.add(monitor.key)
        return state
