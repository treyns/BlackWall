"""Real performance measurements: process CPU/RAM, GPU engine counters, FPS."""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from typing import Callable

import psutil
from PySide6.QtCore import QObject, QTimer, Signal

from core.logger import get_logger
from core.models import PerfSample

log = get_logger("performance")

PDH_FMT_DOUBLE = 0x00000200
PDH_MORE_DATA = 0x800007D2


class _PDH_FMT_COUNTERVALUE_UNION(ctypes.Union):
    _fields_ = [
        ("longValue", wintypes.LONG),
        ("doubleValue", ctypes.c_double),
        ("largeValue", ctypes.c_longlong),
        ("AnsiStringValue", ctypes.c_char_p),
        ("WideStringValue", ctypes.c_wchar_p),
    ]


class _PDH_FMT_COUNTERVALUE(ctypes.Structure):
    _fields_ = [
        ("CStatus", wintypes.DWORD),
        ("u", _PDH_FMT_COUNTERVALUE_UNION),
    ]


class _PdhGpu:
    """GPU load of this process via the Windows "GPU Engine" performance counters.

    Instances of ``\\GPU Engine(*)\\Utilization Percentage`` are expanded once
    every few seconds and the ones belonging to this process are added to a PDH
    query. The array API reports PDH_CSTATUS_INVALID_DATA when any engine is
    unused, therefore single counters are used instead.
    """

    PATH = r"\GPU Engine(*)\Utilization Percentage"

    def __init__(self) -> None:
        self._pdh = None
        self._query = ctypes.c_void_p()
        self._counters: list[ctypes.c_void_p] = []
        self._supported = False
        self._last_expand = 0.0
        self._last_value = 0.0
        self._pid_tag = f"pid_{os.getpid()}_".lower()
        try:
            pdh = ctypes.WinDLL("pdh.dll")
            self._pdh = pdh
            pdh.PdhOpenQueryW.restype = ctypes.c_ulong
            pdh.PdhCloseQuery.restype = ctypes.c_ulong
            pdh.PdhAddCounterW.restype = ctypes.c_ulong
            pdh.PdhCollectQueryData.restype = ctypes.c_ulong
            pdh.PdhGetFormattedCounterValue.restype = ctypes.c_ulong
            pdh.PdhExpandWildCardPathW.restype = ctypes.c_ulong
            if pdh.PdhOpenQueryW(None, 0, ctypes.byref(self._query)) != 0:
                return
            self._supported = bool(self._expand())
        except Exception:  # noqa: BLE001
            self._supported = False

    @property
    def available(self) -> bool:
        return self._supported

    def _expand(self) -> list[str]:
        if self._pdh is None:
            return []
        size = wintypes.DWORD(0)
        status = self._pdh.PdhExpandWildCardPathW(None, self.PATH, None,
                                                  ctypes.byref(size), 0)
        if status not in (0, PDH_MORE_DATA) or not size.value:
            return []
        buffer = ctypes.create_unicode_buffer(size.value)
        status = self._pdh.PdhExpandWildCardPathW(None, self.PATH, buffer,
                                                  ctypes.byref(size), 0)
        if status != 0:
            return []
        array = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_wchar))
        paths: list[str] = []
        index = 0
        length = size.value
        while index < length:
            chars: list[str] = []
            while index < length and array[index] != "\x00":
                chars.append(array[index])
                index += 1
            index += 1
            text = "".join(chars)
            if text:
                paths.append(text)
            elif paths:
                break
        return paths

    def _rebuild(self) -> None:
        paths = self._expand()
        machine = os.environ.get("COMPUTERNAME", "")
        prefix = f"\\\\{machine}\\" if machine else ""
        mine: list[str] = []
        for path in paths:
            if self._pid_tag in path.lower():
                local = path
                if prefix and path.startswith(prefix):
                    local = "\\" + path[len(prefix):]
                mine.append(local)
        try:
            if self._query:
                self._pdh.PdhCloseQuery(self._query)
        except Exception:  # noqa: BLE001
            pass
        self._query = ctypes.c_void_p()
        self._counters = []
        if self._pdh.PdhOpenQueryW(None, 0, ctypes.byref(self._query)) != 0:
            self._query = ctypes.c_void_p()
            return
        for path in mine:
            counter = ctypes.c_void_p()
            if self._pdh.PdhAddCounterW(self._query, path, 0,
                                        ctypes.byref(counter)) == 0:
                self._counters.append(counter)

    def process_gpu(self) -> float | None:
        if not self._supported or self._pdh is None or not self._query:
            return None
        now = time.monotonic()
        rebuild = False
        if not self._counters:
            rebuild = now - self._last_expand > 2.0
        elif now - self._last_expand > 30.0:
            rebuild = True
        if rebuild:
            self._last_expand = now
            self._rebuild()
            # A freshly added PDH counter needs one collect before its value is
            # meaningful; keep the previous value for this tick.
            return self._last_value
        if not self._counters:
            return 0.0
        if self._pdh.PdhCollectQueryData(self._query) != 0:
            return self._last_value
        total = 0.0
        for counter in self._counters:
            value = _PDH_FMT_COUNTERVALUE()
            status = self._pdh.PdhGetFormattedCounterValue(
                counter, PDH_FMT_DOUBLE, None, ctypes.byref(value))
            if status == 0:
                total += float(value.u.doubleValue)
        self._last_value = max(0.0, min(100.0, total))
        return self._last_value


class PerformanceMonitor(QObject):
    sample_ready = Signal(object)  # PerfSample

    def __init__(self, interval_ms: int = 1000, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process = psutil.Process()
        self._process.cpu_percent(None)
        self._last_sample = PerfSample()
        self._fps_provider: Callable[[], float] | None = None
        self._gpu = _PdhGpu()
        self._cores = max(1, psutil.cpu_count(logical=True) or 1)
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._sample)

    # ------------------------------------------------------------------ public
    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def latest(self) -> PerfSample:
        return self._last_sample

    def set_fps_provider(self, provider: Callable[[], float] | None) -> None:
        self._fps_provider = provider

    def gpu_available(self) -> bool:
        return self._gpu.available

    # ---------------------------------------------------------------- internal
    def _sample(self) -> None:
        try:
            process_cpu = self._process.cpu_percent(None)
            memory = self._process.memory_info().rss / (1024 * 1024)
            system_cpu = psutil.cpu_percent(None)
            system_ram = psutil.virtual_memory().percent
            fps = 0.0
            if self._fps_provider is not None:
                try:
                    fps = float(self._fps_provider())
                except Exception:  # noqa: BLE001
                    fps = 0.0
            sample = PerfSample(
                cpu=process_cpu / self._cores,
                ram_mb=memory,
                gpu=self._gpu.process_gpu(),
                fps=fps,
                timestamp=time.time(),
                system_cpu=system_cpu,
                system_ram=system_ram,
            )
            self._last_sample = sample
            self.sample_ready.emit(sample)
        except Exception:  # noqa: BLE001
            log.exception("performance sampling failed")

