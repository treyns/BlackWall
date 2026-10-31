"""Win32 desktop-layer integration (WorkerW) and monitor helpers."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.windll.user32
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowExW.restype = wintypes.HWND
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SetParent.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.SetWindowLongW.restype = wintypes.LONG
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.GetSystemMetrics.restype = ctypes.c_int

GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WM_SPAWN_WORKERW = 0x052C
SMTO_ABORTIFHUNG = 0x0002
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
GA_PARENT = 1

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def virtual_origin() -> tuple[int, int]:
    return user32.GetSystemMetrics(SM_XVIRTUALSCREEN), user32.GetSystemMetrics(SM_YVIRTUALSCREEN)


def virtual_size() -> tuple[int, int]:
    return user32.GetSystemMetrics(SM_CXVIRTUALSCREEN), user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)


def spawn_workerw() -> None:
    """Ask Explorer to create the wallpaper WorkerW layer behind desktop icons."""
    result = wintypes.DWORD(0)
    progman = user32.FindWindowW("Progman", None)
    user32.SendMessageTimeoutW(progman, WM_SPAWN_WORKERW, 0xD, 0x1, SMTO_ABORTIFHUNG,
                               500, ctypes.byref(result))
    user32.SendMessageTimeoutW(0xFFFF, WM_SPAWN_WORKERW, 0xD, 0x1, SMTO_ABORTIFHUNG,
                               500, ctypes.byref(result))


def find_wallpaper_workerw() -> int:
    """Handle of the WorkerW window that sits BEHIND the desktop icons."""
    spawn_workerw()
    found: list[int] = []

    def callback(hwnd, lparam):
        if user32.FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None):
            sibling = user32.FindWindowExW(0, hwnd, "WorkerW", None)
            if sibling:
                found.append(sibling)
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    if found:
        return int(found[0])
    # Fallback: top-level WorkerW without SHELLDLL_DefView child.
    workerw = user32.FindWindowExW(0, 0, "WorkerW", None)
    while workerw:
        if not user32.FindWindowExW(workerw, 0, "SHELLDLL_DefView", None):
            return int(workerw)
        workerw = user32.FindWindowExW(0, workerw, "WorkerW", None)
    return 0


def attach_child(hwnd: int, workerw: int, x: int, y: int, width: int, height: int) -> bool:
    """Reparent a foreign top-level window into WorkerW and position it."""
    if not hwnd or not workerw or not user32.IsWindow(workerw):
        return False
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    user32.SetWindowLongW(hwnd, GWL_STYLE, (style & ~WS_POPUP) | WS_CHILD)
    previous = user32.SetParent(hwnd, workerw)
    if user32.GetAncestor(hwnd, GA_PARENT) != workerw:
        return False
    origin_x, origin_y = virtual_origin()
    ok = bool(user32.SetWindowPos(hwnd, None, x - origin_x, y - origin_y,
                                  width, height,
                                  SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW))
    return ok


def detach_child(hwnd: int) -> None:
    if not hwnd or not user32.IsWindow(hwnd):
        return
    try:
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        user32.SetWindowLongW(hwnd, GWL_STYLE, (style & ~WS_CHILD) | WS_POPUP)
        user32.SetParent(hwnd, 0)
    except Exception:  # noqa: BLE001
        pass


def move_child(hwnd: int, x: int, y: int, width: int, height: int) -> None:
    if not hwnd or not user32.IsWindow(hwnd):
        return
    origin_x, origin_y = virtual_origin()
    user32.SetWindowPos(hwnd, None, x - origin_x, y - origin_y, width, height,
                        SWP_NOZORDER | SWP_NOACTIVATE)


def clear_desktop_children_except(keep: set[int]) -> None:
    """Remove leftovers of previous runs from the wallpaper layer."""
    workerw = find_wallpaper_workerw()
    if not workerw:
        return
    child = user32.FindWindowExW(workerw, 0, None, None)
    while child:
        if int(child) not in keep:
            try:
                detach_child(int(child))
            except Exception:  # noqa: BLE001
                pass
        child = user32.FindWindowExW(workerw, child, None, None)
