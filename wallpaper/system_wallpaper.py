"""Set static images as normal Windows wallpapers (per monitor when possible)."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from core.logger import get_logger

log = get_logger("system-wallpaper")

user32 = ctypes.windll.user32
ole32 = ctypes.WinDLL("ole32")

SPI_SETDESKWALLPAPER = 0x0014
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02
CLSCTX_ALL = 0x17
DWPOS_FILL = 4
S_OK = 0

COINIT_APARTMENTTHREADED = 0x2


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(text: str) -> GUID:
    import uuid

    value = uuid.UUID(text)
    guid = GUID()
    guid.Data1 = value.time_low
    guid.Data2 = value.time_mid
    guid.Data3 = value.time_hi_version
    for index, byte in enumerate(value.bytes[8:]):
        guid.Data4[index] = byte
    return guid


CLSID_DesktopWallpaper = _guid("{C2CF3110-460E-4fc1-B9D0-8A1C0C9CC4BD}")
IID_IDesktopWallpaper = _guid("{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}")

ole32.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                   ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
ole32.CoCreateInstance.restype = ctypes.c_long
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
ole32.CoTaskMemFree.restype = None


def _free_com_string(value) -> None:  # noqa: ANN001
    try:
        ole32.CoTaskMemFree(ctypes.cast(value, ctypes.c_void_p))
    except Exception:  # noqa: BLE001
        pass


class _RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class DesktopWallpaper:
    """Thin ctypes wrapper around IDesktopWallpaper (Windows 8+)."""

    def __init__(self) -> None:
        self._ptr = ctypes.c_void_p()
        self._available = False
        try:
            ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
            result = ole32.CoCreateInstance(
                ctypes.byref(CLSID_DesktopWallpaper), None, CLSCTX_ALL,
                ctypes.byref(IID_IDesktopWallpaper), ctypes.byref(self._ptr))
            self._available = result == S_OK and bool(self._ptr.value)
        except Exception:  # noqa: BLE001
            self._available = False
        if not self._available:
            log.info("IDesktopWallpaper is not available - per-monitor static wallpaper disabled")

    @property
    def available(self) -> bool:
        return self._available

    def _vtable_method(self, index: int, restype, *argtypes):
        vtable = ctypes.cast(self._ptr,
                             ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
        return prototype(vtable[index])

    def _release(self) -> None:
        if self._available and self._ptr.value:
            try:
                release = self._vtable_method(2, ctypes.c_ulong)
                release(self._ptr)
            except Exception:  # noqa: BLE001
                pass
            self._ptr = ctypes.c_void_p()
            self._available = False

    def __del__(self) -> None:
        try:
            self._release()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ basics
    def set_position(self, position: int = DWPOS_FILL) -> None:
        if not self._available:
            return
        try:
            method = self._vtable_method(10, ctypes.c_long, ctypes.c_int)
            method(self._ptr, position)
        except Exception:  # noqa: BLE001
            log.exception("SetPosition failed")

    def monitor_count(self) -> int:
        if not self._available:
            return 0
        try:
            count = ctypes.c_uint(0)
            method = self._vtable_method(6, ctypes.c_long, ctypes.POINTER(ctypes.c_uint))
            if method(self._ptr, ctypes.byref(count)) == S_OK:
                return int(count.value)
        except Exception:  # noqa: BLE001
            pass
        return 0

    def monitor_id_at(self, index: int) -> str | None:
        if not self._available:
            return None
        try:
            buffer = ctypes.c_wchar_p()
            method = self._vtable_method(
                5, ctypes.c_long, ctypes.c_uint, ctypes.POINTER(ctypes.c_wchar_p))
            if method(self._ptr, ctypes.c_uint(index), ctypes.byref(buffer)) == S_OK:
                value = buffer.value
                if buffer:
                    _free_com_string(buffer)
                return value
        except Exception:  # noqa: BLE001
            pass
        return None

    def monitor_rect(self, monitor_id: str) -> tuple[int, int, int, int] | None:
        if not self._available:
            return None
        try:
            rect = _RECT()
            method = self._vtable_method(7, ctypes.c_long, ctypes.c_wchar_p,
                                         ctypes.POINTER(_RECT))
            if method(self._ptr, ctypes.c_wchar_p(monitor_id), ctypes.byref(rect)) == S_OK:
                return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
        except Exception:  # noqa: BLE001
            pass
        return None

    def id_for_rect(self, x: int, y: int, width: int, height: int) -> str | None:
        for index in range(self.monitor_count()):
            monitor_id = self.monitor_id_at(index)
            if not monitor_id:
                continue
            rect = self.monitor_rect(monitor_id)
            if rect and abs(rect[0] - x) <= 2 and abs(rect[1] - y) <= 2:
                return monitor_id
        return None

    def set_wallpaper(self, monitor_id: str | None, path: str) -> bool:
        if not self._available:
            return False
        try:
            method = self._vtable_method(3, ctypes.c_long, ctypes.c_wchar_p, ctypes.c_wchar_p)
            result = method(self._ptr,
                            ctypes.c_wchar_p(monitor_id) if monitor_id else None,
                            ctypes.c_wchar_p(path))
            return result == S_OK
        except Exception:  # noqa: BLE001
            log.exception("SetWallpaper failed")
            return False

    def get_wallpaper(self, monitor_id: str | None = None) -> str | None:
        if not self._available:
            return None
        try:
            buffer = ctypes.c_wchar_p()
            method = self._vtable_method(4, ctypes.c_long, ctypes.c_wchar_p,
                                         ctypes.POINTER(ctypes.c_wchar_p))
            result = method(self._ptr,
                            ctypes.c_wchar_p(monitor_id) if monitor_id else None,
                            ctypes.byref(buffer))
            if result == S_OK and buffer.value:
                value = buffer.value
                if buffer:
                    _free_com_string(buffer)
                return value
        except Exception:  # noqa: BLE001
            pass
        return None


_DESKTOP: DesktopWallpaper | None = None


def desktop_wallpaper() -> DesktopWallpaper:
    global _DESKTOP
    if _DESKTOP is None:
        _DESKTOP = DesktopWallpaper()
    return _DESKTOP


def set_static_wallpaper_all(path: str) -> bool:
    """Set the same image on every monitor using the plain Windows API."""
    if not path or not os.path.exists(path):
        return False
    result = user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, path, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
    if result:
        _set_style_fill()
    return bool(result)


def _set_style_fill() -> None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, "10")
            winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, "0")
    except OSError:
        pass


def set_static_wallpaper_monitor(monitor, path: str) -> bool:
    """Set one image on a single monitor; falls back to the global wallpaper."""
    if not path or not os.path.exists(path):
        return False
    wallpaper = desktop_wallpaper()
    if wallpaper.available:
        monitor_id = wallpaper.id_for_rect(monitor.x, monitor.y, monitor.width,
                                           monitor.height)
        if monitor_id:
            if wallpaper.set_wallpaper(monitor_id, path):
                wallpaper.set_position(DWPOS_FILL)
                return True
    return False


def get_previous_wallpaper(monitor) -> str | None:
    wallpaper = desktop_wallpaper()
    if wallpaper.available:
        monitor_id = wallpaper.id_for_rect(monitor.x, monitor.y, monitor.width,
                                           monitor.height)
        if monitor_id:
            value = wallpaper.get_wallpaper(monitor_id)
            if value:
                return value
    return wallpaper.get_wallpaper(None)


def restore_wallpaper(monitor, path: str | None) -> None:
    if not path:
        return
    if set_static_wallpaper_monitor(monitor, path):
        return
    set_static_wallpaper_all(path)

