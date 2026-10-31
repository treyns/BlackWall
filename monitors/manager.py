"""Monitor discovery and change tracking.

Uses Qt's screen API (reliable, DPI-aware) plus a light poll so resolution
changes and hot-plugging are picked up even when no Qt signal is emitted.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from core.logger import get_logger
from core.models import MonitorInfo

log = get_logger("monitors")


class MonitorManager(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._monitors: list[MonitorInfo] = []
        self._signature: tuple = ()
        self._poll = QTimer(self)
        self._poll.setInterval(2000)
        self._poll.timeout.connect(lambda: self.refresh(force=False))
        self.refresh(force=True)

    # ------------------------------------------------------------------ public
    def monitors(self) -> list[MonitorInfo]:
        return list(self._monitors)

    def primary(self) -> MonitorInfo | None:
        for monitor in self._monitors:
            if monitor.primary:
                return monitor
        return self._monitors[0] if self._monitors else None

    def get(self, key: str) -> MonitorInfo | None:
        for monitor in self._monitors:
            if monitor.key == key:
                return monitor
        return None

    def by_name(self, name: str) -> MonitorInfo | None:
        for monitor in self._monitors:
            if monitor.name == name:
                return monitor
        return None

    def start_watching(self) -> None:
        self._poll.start()

    def stop_watching(self) -> None:
        self._poll.stop()

    def refresh(self, force: bool = False) -> bool:
        app = QApplication.instance()
        monitors: list[MonitorInfo] = []
        if app is not None:
            primary_screen = app.primaryScreen()
            for index, screen in enumerate(app.screens()):
                geometry = screen.geometry()
                monitors.append(MonitorInfo(
                    key=f"{screen.name()}|{geometry.x()},{geometry.y()},"
                        f"{geometry.width()}x{geometry.height()}",
                    name=screen.name() or f"DISPLAY{index + 1}",
                    x=geometry.x(),
                    y=geometry.y(),
                    width=geometry.width(),
                    height=geometry.height(),
                    primary=screen == primary_screen,
                    refresh=float(screen.refreshRate() or 60),
                    dpr=float(screen.devicePixelRatio() or 1),
                ))
        signature = tuple((m.key, m.x, m.y, m.width, m.height, m.primary) for m in monitors)
        self._monitors = monitors
        changed = force or signature != self._signature
        self._signature = signature
        if changed:
            log.info("monitors: %s", "; ".join(
                f"{m.name} {m.resolution} @{m.refresh:.0f}Hz" for m in monitors))
            self.changed.emit()
        return changed

    def screen_for(self, monitor: MonitorInfo):
        """Return the QScreen that matches a MonitorInfo (by geometry/name)."""
        app = QApplication.instance()
        if app is None:
            return None
        for screen in app.screens():
            geometry = screen.geometry()
            if (screen.name() == monitor.name
                    and geometry.x() == monitor.x and geometry.y() == monitor.y
                    and geometry.width() == monitor.width
                    and geometry.height() == monitor.height):
                return screen
        for screen in app.screens():
            geometry = screen.geometry()
            if (geometry.x() == monitor.x and geometry.y() == monitor.y
                    and geometry.width() == monitor.width
                    and geometry.height() == monitor.height):
                return screen
        return None
