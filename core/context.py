"""Application context: a single object every page receives."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from config.settings import Settings
from core.database import Database
from core.i18n import tr
from core.logger import get_logger
from core.models import Assignment, MediaItem, MonitorInfo
from browser.detector import AutoPauseDetector
from downloads.manager import DownloadManager
from importers.manager import ImportManager
from importers.merge import MergeManager
from library.manager import LibraryManager
from monitors.manager import MonitorManager
from performance.adaptive import AdaptiveQualityController
from performance.monitor import PerformanceMonitor
from recommendations.engine import RecommendationEngine
from search.manager import SearchManager
from wallpaper.engine import WallpaperManager

log = get_logger("context")


class AppContext(QObject):
    status_changed = Signal(str, str)       # text, state (ok/warn/error/paused/off)
    navigate_requested = Signal(str)        # page key
    assignments_changed = Signal()
    language_changed = Signal()

    def __init__(self, settings: Settings, db: Database,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.db = db
        self.main_window = None  # set by MainWindow

        self.monitors = MonitorManager(self)
        self.library = LibraryManager(db, settings, self)
        self.downloads = DownloadManager(db, settings, self.library, self)
        self.search = SearchManager(settings, db, self)
        self.recommendations = RecommendationEngine(self.search, settings, db, self)
        self.imports = ImportManager(db, settings, self.library, self.monitors, self)
        self.merge = MergeManager(db, settings, self.library, self.monitors, self)
        self.performance = PerformanceMonitor(parent=self)
        self.detector = AutoPauseDetector(settings)
        self.wallpaper = WallpaperManager(settings, db, self.monitors, self.library, self)
        self.adaptive = AdaptiveQualityController(settings)

        self.wallpaper.state_changed.connect(self.assignments_changed.emit)
        self.wallpaper.state_changed.connect(self._refresh_status)
        self.wallpaper.info.connect(lambda message: self.notify(tr(message), "ok"))
        self.monitors.changed.connect(self._on_monitors_changed)
        self.library.changed.connect(self.assignments_changed.emit)
        self.performance.sample_ready.connect(self._on_performance_sample)
        self.settings.add_listener(self._on_setting_changed)

    # ---------------------------------------------------------- adaptive quality
    def _on_performance_sample(self, sample) -> None:  # noqa: ANN001
        if self.wallpaper.active_count() <= 0:
            if self.wallpaper.adaptive_level != 0:
                self.wallpaper.set_adaptive_level(0)
            return
        active = not self.wallpaper.paused and not self.wallpaper.auto_paused
        target = float(self.wallpaper.effective_fps_cap)
        level = self.adaptive.update(sample, target, active)
        if level is None:
            return
        self.wallpaper.set_adaptive_level(level)
        if level > 0:
            self.notify(tr("Quality reduced automatically"),
                        "warn")
        else:
            self.notify(tr("Playback quality restored"), "ok")

    def _on_setting_changed(self, key: str) -> None:
        if key == "performance.adaptive_quality":
            enabled = bool(self.settings.get("performance.adaptive_quality", True))
            self.adaptive.reset()
            self.wallpaper.on_adaptive_enabled_changed(enabled)
            return
        if key == "playback.manual_quality":
            if not self.adaptive.enabled:
                self.wallpaper.apply_quality_mode()
            return
        if key in ("performance.fps_cap", "performance.mode"):
            if not self.adaptive.enabled and self.wallpaper.adaptive_level != 0:
                self.wallpaper.set_adaptive_level(0)

    # ------------------------------------------------------------------ helpers
    def t(self, text: str, **kwargs) -> str:
        return tr(text, **kwargs)

    def notify(self, text: str, state: str = "ok") -> None:
        self.status_changed.emit(text, state)

    def navigate(self, page_key: str) -> None:
        self.navigate_requested.emit(page_key)

    # ------------------------------------------------------------- wallpapers
    def install_media(self, media_id: int, monitor_key: str | None = None) -> bool:
        item = self.db.get_media(media_id)
        if item is None:
            self.notify(tr("Wallpaper not found"), "error")
            return False
        if not item.file_path or not item.is_local:
            self.notify(tr("Download the wallpaper first"), "warn")
            return False
        ok = self.wallpaper.apply(item, monitor_key)
        if ok:
            self.db.touch_used(media_id)
            target = self.monitors.get(monitor_key) if monitor_key else self.monitors.primary()
            name = target.name if target else tr("all monitors")
            self.notify(tr("Wallpaper applied to {monitor}", monitor=name), "ok")
        return ok

    def apply_to_all(self, media_id: int) -> bool:
        item = self.db.get_media(media_id)
        if item is None or not item.is_local:
            self.notify(tr("Download the wallpaper first"), "warn")
            return False
        ok = False
        for monitor in self.monitors.monitors():
            ok = self.wallpaper.apply(item, monitor.key) or ok
        if ok:
            self.db.touch_used(media_id)
            self.notify(tr("Wallpaper applied to all monitors"), "ok")
        return ok

    def assignment_for(self, monitor_key: str) -> Assignment | None:
        return self.wallpaper.assignment_for(monitor_key)

    def set_assignment_fit(self, monitor_key: str, fit: str) -> bool:
        ok = self.wallpaper.set_assignment_fit(monitor_key, fit)
        if ok:
            self.notify(self.t("Display mode updated for this monitor"), "ok")
        return ok

    def set_assignment_quality(self, monitor_key: str, quality: str) -> bool:
        ok = self.wallpaper.set_assignment_quality(monitor_key, quality)
        if ok:
            self.notify(self.t("Video quality updated for this monitor"), "ok")
        return ok

    def set_assignment_fps(self, monitor_key: str, fps: int) -> bool:
        ok = self.wallpaper.set_assignment_fps(monitor_key, fps)
        if ok:
            self.notify(self.t("FPS limit updated for this monitor"), "ok")
        return ok

    def set_assignment_audio(self, monitor_key: str, muted: bool, volume: int) -> bool:
        ok = self.wallpaper.set_assignment_audio(monitor_key, muted, volume)
        if ok:
            self.notify(self.t("Sound settings updated for this monitor"), "ok")
        return ok

    def toggle_monitor_paused(self, monitor_key: str) -> bool:
        paused = self.wallpaper.toggle_monitor_paused(monitor_key)
        self.notify(self.t("Paused on this monitor") if paused
                    else self.t("Playing on this monitor"),
                    "paused" if paused else "ok")
        return paused

    def reprocess_media(self, media_id: int) -> None:
        item = self.db.get_media(media_id)
        if item is None or not item.file_path:
            self.notify(tr("Wallpaper not found"), "error")
            return
        self.imports.reprocess(media_id)
        self.notify(tr("Reprocessing video…"), "ok")

    def set_media_fit(self, media_id: int, fit: str) -> bool:
        ok = self.wallpaper.set_media_fit(media_id, fit)
        if ok:
            self.notify(self.t("Display mode updated for this wallpaper"), "ok")
        return ok

    def primary_monitor(self) -> MonitorInfo | None:
        return self.monitors.primary()

    # ------------------------------------------------------------------ status
    def _refresh_status(self) -> None:
        if self.wallpaper.paused:
            self.notify(tr("Wallpapers paused"), "paused")
        elif self.wallpaper.active_count() > 0:
            self.notify(tr("Wallpapers active"), "ok")
        else:
            self.notify(tr("No wallpaper assigned"), "off")

    def _on_monitors_changed(self) -> None:
        self.wallpaper.refresh()
        self.assignments_changed.emit()

    # ----------------------------------------------------------------- cleanup
    def shutdown(self) -> None:
        try:
            self.downloads.shutdown()
            self.imports.cancel()
            self.merge.cancel()
            self.wallpaper.shutdown()
            self.performance.stop()
            self.monitors.stop_watching()
        except Exception:  # noqa: BLE001
            log.exception("shutdown error")
        finally:
            self.db.close()
            self.settings.save()

