"""System integration: autostart, single instance."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from core.logger import get_logger

log = get_logger("system")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_RUN_NAME = "BlackWall"


def _launcher() -> str:
    executable = sys.executable
    directory = Path(executable).parent
    for name in ("BlackWall.exe", "pythonw.exe"):
        candidate = directory / name
        if candidate.exists():
            return str(candidate)
    return executable


def autostart_command() -> str:
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{_launcher()}" "{main_py}" --minimized'


def is_autostart_enabled() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _type = winreg.QueryValueEx(key, APP_RUN_NAME)
            return bool(value)
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    """Enable/disable launch at Windows login. Returns the effective state."""
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_RUN_NAME, 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_RUN_NAME)
                except FileNotFoundError:
                    pass
        return enabled
    except OSError:
        log.exception("autostart change failed")
        return is_autostart_enabled()
