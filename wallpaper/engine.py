"""Wallpaper engine: per-monitor desktop windows, playback and auto-pause."""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from browser.detector import AutoPauseDetector, PauseState
from config import paths
from config.constants import (FIT_MODES, PERFORMANCE_MODES, VIDEO_QUALITY_WIDTHS)
from core.logger import get_logger
from core.models import Assignment, MediaItem, MonitorInfo
from library.lightcopy import ADAPTIVE_WIDTH, LightCopyManager
from wallpaper import system_wallpaper, winapi
from wallpaper.view import MediaView

log = get_logger("wallpaper")

MAX_RETRY_LOG = 3


class DesktopWindow(QWidget):
    """Borderless window that is reparented into the desktop WorkerW layer."""

    def __init__(self, monitor: MonitorInfo, screen) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.monitor = monitor
        self._hwnd = 0
        self.attached = False
        self.view = MediaView(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.view)
        if screen is not None:
            self.setGeometry(screen.geometry())
        else:
            self.setGeometry(monitor.x, monitor.y, monitor.width, monitor.height)
        self.setWindowTitle("BlackWall Wallpaper")

    # ------------------------------------------------------------------ native
    def native_handle(self) -> int:
        if not self._hwnd:
            self._hwnd = int(self.winId())
        return self._hwnd

    def attach(self, workerw: int) -> bool:
        """Reparent into the desktop layer before the window ever becomes visible.

        Showing the window first would flash a black rectangle over the monitor
        for a moment, which is exactly what the startup should avoid.
        """
        if not workerw:
            return False
        hwnd = self.native_handle()
        dpr = self.monitor.dpr or 1.0
        width = max(2, int(round(self.monitor.width * dpr)))
        height = max(2, int(round(self.monitor.height * dpr)))
        attached = winapi.attach_child(hwnd, workerw, self.monitor.x, self.monitor.y,
                                       width, height)
        if attached:
            # Show only after SetParent: the window is already a child of the
            # WorkerW layer, so it appears behind the desktop icons, not above them.
            if not self.isVisible():
                self.show()
            winapi.move_child(hwnd, self.monitor.x, self.monitor.y, width, height)
        self.attached = attached
        return attached

    def update_geometry(self, monitor: MonitorInfo, screen) -> None:
        self.monitor = monitor
        if screen is not None:
            self.setGeometry(screen.geometry())
        if self.attached:
            dpr = monitor.dpr or 1.0
            winapi.move_child(self.native_handle(), monitor.x, monitor.y,
                              int(round(monitor.width * dpr)),
                              int(round(monitor.height * dpr)))

    def detach(self) -> None:
        if self._hwnd:
            winapi.detach_child(self._hwnd)
        self.attached = False
        self.hide()

    def destroy(self) -> None:
        try:
            self.view.shutdown()
        except Exception:  # noqa: BLE001
            pass
        self.detach()
        self.deleteLater()


class WallpaperManager(QObject):
    state_changed = Signal()
    error = Signal(str)
    adaptive_changed = Signal(int)
    info = Signal(str)

    def __init__(self, settings, db, monitors, library, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.db = db
        self.monitors = monitors
        self.library = library
        self._windows: dict[str, DesktopWindow] = {}
        self._assignments: dict[str, Assignment] = {}
        self._previous_wallpapers: dict[str, str | None] = {}
        self._user_paused = False
        self._auto_paused = False
        self._pause_state = PauseState()
        self._fps_cap = int(settings.get("performance.fps_cap", 30) or 30)
        self._mode = str(settings.get("performance.mode", "balanced") or "balanced")
        self._adaptive_level = 0
        self._render_scale = 1.0
        self._view_sources: dict[str, str] = {}
        self._light_failed: set[tuple[str, int]] = set()
        self._light = LightCopyManager(paths.CACHE_DIR / "optimized", self)
        self._light.ready.connect(self._on_light_ready)
        self._light.failed.connect(self._on_light_failed)
        self._detector = AutoPauseDetector(settings)
        self._workerw = 0
        self._attach_warned = 0
        self._last_pause_signature: tuple = ()
        self._load_assignments()
        self._capture_previous_wallpapers()

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self.monitors.changed.connect(self.refresh)
        QTimer.singleShot(500, self.refresh)

    # ------------------------------------------------------------------ public
    def assignments(self) -> dict[str, Assignment]:
        return dict(self._assignments)

    def assignment_for(self, monitor_key: str) -> Assignment | None:
        return self._assignments.get(monitor_key)

    @property
    def paused(self) -> bool:
        return self._user_paused

    @property
    def auto_paused(self) -> bool:
        return self._auto_paused

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def fps_cap(self) -> int:
        return self._fps_cap

    @property
    def adaptive_level(self) -> int:
        return self._adaptive_level

    @property
    def render_scale(self) -> float:
        return self._render_scale

    @property
    def effective_fps_cap(self) -> int:
        multiplier = {0: 1.0, 1: 0.66, 2: 0.5}.get(self._adaptive_level, 1.0)
        return max(8, int(round(self._fps_cap * multiplier)))

    def light_copy_pending(self) -> bool:
        return self._light.pending_count() > 0

    @property
    def adaptive_enabled(self) -> bool:
        return bool(self.settings.get("performance.adaptive_quality", True))

    @property
    def manual_quality(self) -> str:
        value = str(self.settings.get("playback.manual_quality", "original") or "original")
        return value if value in VIDEO_QUALITY_WIDTHS else "original"

    @property
    def manual_quality_width(self) -> int:
        return int(VIDEO_QUALITY_WIDTHS.get(self.manual_quality, 0))

    def set_manual_quality(self, quality: str) -> None:
        if quality not in VIDEO_QUALITY_WIDTHS:
            return
        self.settings.set("playback.manual_quality", quality)
        if not self.adaptive_enabled:
            self.apply_quality_mode()

    def apply_quality_mode(self) -> None:
        """Apply the user's manual quality choice (only when adaptive is off)."""
        if self.adaptive_enabled:
            return
        for key, assignment in list(self._assignments.items()):
            if assignment.kind != "video" or not assignment.file_path:
                continue
            target = self._manual_source_for(assignment)
            if target and self._view_sources.get(key) != target:
                self._switch_view_source(key, target)
            if target == assignment.file_path:
                self._request_manual_copy(assignment)
        self.state_changed.emit()

    def _manual_source_for(self, assignment: Assignment) -> str:
        width = self._desired_width(assignment)
        if width <= 0:
            return assignment.file_path
        light = self._light.path_for(assignment.file_path, width)
        return light or assignment.file_path

    def _request_manual_copy(self, assignment: Assignment) -> None:
        width = self._desired_width(assignment)
        if width <= 0 or not assignment.file_path:
            return
        if (assignment.file_path, width) in self._light_failed:
            return
        if self._light.path_for(assignment.file_path, width):
            return
        if self._light.is_pending(assignment.file_path, width):
            return
        self.info.emit("Preparing the selected video quality…")
        self._light.request(assignment.file_path, width)

    def set_adaptive_level(self, level: int) -> None:
        level = max(0, min(2, int(level)))
        if level == self._adaptive_level:
            return
        self._adaptive_level = level
        self._render_scale = {0: 1.0, 1: 0.85, 2: 0.7}.get(level, 1.0)
        self._apply_quality()
        if level >= 2:
            self._prepare_light_copies()
        elif self.adaptive_enabled:
            self._restore_original_sources()
        else:
            self.apply_quality_mode()
        self.adaptive_changed.emit(level)
        self.state_changed.emit()

    def on_adaptive_enabled_changed(self, enabled: bool) -> None:
        """React to the user switching the automatic quality mode on/off."""
        if enabled:
            changed = self._adaptive_level != 0
            self._adaptive_level = 0
            self._render_scale = 1.0
            self._apply_quality()
            self._restore_original_sources()
            if changed:
                self.adaptive_changed.emit(0)
            self.state_changed.emit()
        else:
            self.apply_quality_mode()

    def _apply_quality(self) -> None:
        for key, window in self._windows.items():
            assignment = self._assignments.get(key)
            fps = self._fps_for(assignment) if assignment is not None else self.effective_fps_cap
            window.view.set_fps_cap(fps)
            window.view.set_render_scale(self._render_scale)

    def clear_quality_cache(self) -> None:
        self._light.clear()
        self._light_failed.clear()
        self._restore_original_sources()

    def _desired_width(self, assignment: Assignment) -> int:
        """Requested width for a single assignment, 0 = source file."""
        if assignment.kind != "video" or not assignment.file_path:
            return 0
        width = 0
        if self._adaptive_level >= 2:
            width = ADAPTIVE_WIDTH
            quality = assignment.quality or "original"
            if quality != "original":
                width = min(width, int(VIDEO_QUALITY_WIDTHS.get(quality, width) or width))
        elif not self.adaptive_enabled:
            quality = assignment.quality or "original"
            if quality != "original":
                width = int(VIDEO_QUALITY_WIDTHS.get(quality, 0))
            else:
                width = self.manual_quality_width
        if width <= 0:
            return 0
        item = self.db.get_media(assignment.media_id) if assignment.media_id else None
        source_width = int(item.width) if item is not None else 0
        if source_width and width >= source_width:
            return 0
        return width

    def _source_for(self, assignment: Assignment) -> str:
        base = assignment.file_path
        width = self._desired_width(assignment)
        if width <= 0 or not base:
            return base
        light = self._light.path_for(base, width)
        if light:
            return light
        if ((base, width) not in self._light_failed
                and not self._light.is_pending(base, width)):
            self.info.emit("Preparing the selected video quality…")
            self._light.request(base, width)
        return base

    def _prepare_light_copies(self) -> None:
        for key, assignment in self._assignments.items():
            if assignment.kind != "video" or not assignment.file_path:
                continue
            if (assignment.file_path, ADAPTIVE_WIDTH) in self._light_failed:
                continue
            media = self.db.get_media(assignment.media_id) if assignment.media_id else None
            width = media.width if media is not None else 0
            if width and width <= 1400:
                continue  # already small - FPS limit and scaling are enough
            light = self._light.path_for(assignment.file_path, ADAPTIVE_WIDTH)
            if light:
                window = self._windows.get(key)
                if window is not None:
                    self._switch_view_source(key, light,
                                             "a lighter copy is already available")
                continue
            if self._light.is_pending(assignment.file_path, ADAPTIVE_WIDTH):
                continue
            self.info.emit("Preparing a lightweight video copy…")
            self._light.request(assignment.file_path, ADAPTIVE_WIDTH)

    def _switch_view_source(self, key: str, source: str, reason: str = "") -> None:
        window = self._windows.get(key)
        assignment = self._assignments.get(key)
        if window is None or assignment is None or not source:
            return
        if self._view_sources.get(key) == source:
            return
        window.view.set_source(
            source, assignment.kind, fit=assignment.fit, muted=assignment.muted,
            volume=assignment.volume, speed=assignment.speed,
            fps_cap=self._fps_for(assignment),
            loop=bool(self.settings.get("playback.loop", True)))
        window.view.set_render_scale(self._render_scale)
        window.view.set_paused(self._should_pause(key))
        self._view_sources[key] = source
        if reason:
            self.info.emit(reason)

    def _restore_original_sources(self) -> None:
        for key, source in list(self._view_sources.items()):
            assignment = self._assignments.get(key)
            if assignment is None:
                self._view_sources.pop(key, None)
                continue
            if source != assignment.file_path:
                self._switch_view_source(key, assignment.file_path)
            else:
                self._view_sources[key] = assignment.file_path

    def _on_light_ready(self, source: str, light_path: str, width: int) -> None:
        self.info.emit("Video quality changed")
        for key, assignment in self._assignments.items():
            if assignment.file_path != source:
                continue
            if self._desired_width(assignment) == int(width):
                self._switch_view_source(key, light_path)

    def _on_light_failed(self, source: str, message: str, width: int) -> None:
        self._light_failed.add((source, int(width)))
        self.info.emit("Could not create a lightweight video copy")

    def active_count(self) -> int:
        return sum(1 for window in self._windows.values() if window.attached)

    def measured_fps(self) -> float:
        values = [window.view.measured_fps() for window in self._windows.values()
                  if window.view.media_kind in ("video", "animation")]
        values = [value for value in values if value > 0]
        return sum(values) / len(values) if values else 0.0

    def status_text(self, monitor_key: str | None = None) -> str:
        paused = self._user_paused
        if monitor_key:
            assignment = self._assignments.get(monitor_key)
            paused = bool(paused or (assignment is not None and assignment.paused))
        if paused:
            return "Paused"
        if self._auto_paused:
            if self._pause_state.idle:
                return "Paused · idle"
            if self._pause_state.on_battery:
                return "Paused · battery"
            return "Paused · fullscreen app"
        if self.active_count() > 0:
            return "Active"
        return "No wallpaper"

    # ------------------------------------------------------------------- apply
    def apply(self, item: MediaItem, monitor_key: str | None = None) -> bool:
        monitors = self.monitors.monitors()
        if not monitors:
            self.error.emit("No monitors detected")
            return False
        if not item.file_path or not os.path.exists(item.file_path):
            self.error.emit(f"File not found: {item.file_path}")
            return False
        if monitor_key:
            targets = [monitor for monitor in monitors if monitor.key == monitor_key]
        else:
            primary = self.monitors.primary()
            targets = [primary] if primary else monitors[:1]
        if not targets:
            self.error.emit("Monitor not found")
            return False

        ok = False
        for monitor in targets:
            ok = self._apply_one(monitor, item) or ok
        if ok:
            self._save_assignments()
            self.state_changed.emit()
        return ok

    def _apply_one(self, monitor: MonitorInfo, item: MediaItem,
                   fit_override: str | None = None) -> bool:
        original_path = str(item.file_path)
        path = original_path
        if (item.kind == "video" and item.optimized_path
                and os.path.exists(item.optimized_path)
                and bool(self.settings.get("import.prefer_optimized", True))):
            path = item.optimized_path
        kind = item.kind
        default_fit = str(item.meta.get("fit") or self.settings.get("playback.fit", "cover")
                          or "cover")
        fit = fit_override if fit_override in FIT_MODES else default_fit
        if fit not in FIT_MODES:
            fit = "cover"
        previous = self._assignments.get(monitor.key)
        same_media = previous is not None and previous.media_id == item.id
        quality = (previous.quality if same_media else
                   str(item.meta.get("quality") or "original"))
        if quality not in VIDEO_QUALITY_WIDTHS:
            quality = "original"
        fps_cap = (int(previous.fps_cap) if same_media else
                   int(item.meta.get("fps_cap") or 0))
        muted = bool(previous.muted) if same_media else bool(
            self.settings.get("playback.muted", True))
        volume = int(previous.volume) if same_media else int(
            self.settings.get("playback.volume", 0) or 0)
        paused = bool(previous.paused) if same_media else False
        speed = float(self.settings.get("playback.speed", 1.0) or 1.0)
        loop = bool(self.settings.get("playback.loop", True))

        assignment = Assignment(
            monitor_key=monitor.key,
            media_id=item.id,
            file_path=path,
            kind=kind,
            fit=fit,
            fit_explicit=False,
            quality=quality,
            fps_cap=fps_cap,
            paused=paused,
            muted=muted,
            volume=volume,
            speed=speed,
            enabled=True,
            source=item.source,
            title=item.title,
        )

        if kind == "image" and fit != "blur":
            if self._set_static(monitor, path):
                self._destroy_window(monitor.key)
                self._assignments[monitor.key] = assignment
                log.info("static wallpaper set on %s: %s", monitor.name, path)
                return True
            # Fall back to rendering the image inside the desktop window.
            kind = "image"

        window = self._ensure_window(monitor)
        if window is None:
            return False
        window.view.error.connect(lambda message, name=monitor.name:
                                  self.error.emit(f"{name}: {message}"))
        source = self._source_for(assignment)
        window.view.set_source(source, kind, fit=fit, muted=muted, volume=volume,
                               speed=speed, fps_cap=self._fps_for(assignment), loop=loop)
        window.view.set_render_scale(self._render_scale)
        window.view.set_paused(self._should_pause(monitor.key))
        self._view_sources[monitor.key] = source
        self._assignments[monitor.key] = assignment
        log.info("wallpaper applied on %s: %s (%s)", monitor.name, source, kind)
        return True

    def _fps_for(self, assignment: Assignment) -> int:
        cap = self.effective_fps_cap
        if assignment.fps_cap and int(assignment.fps_cap) > 0:
            cap = min(cap, int(assignment.fps_cap))
        return max(8, cap)

    def set_assignment_quality(self, monitor_key: str, quality: str) -> bool:
        if quality not in VIDEO_QUALITY_WIDTHS:
            return False
        assignment = self._assignments.get(monitor_key)
        if assignment is None:
            return False
        assignment.quality = quality
        if not self.adaptive_enabled:
            self.apply_quality_mode()
        self._save_assignments()
        self.state_changed.emit()
        return True

    def set_assignment_fps(self, monitor_key: str, fps: int) -> bool:
        assignment = self._assignments.get(monitor_key)
        if assignment is None:
            return False
        assignment.fps_cap = max(0, min(120, int(fps)))
        window = self._windows.get(monitor_key)
        if window is not None:
            window.view.set_fps_cap(self._fps_for(assignment))
        self._save_assignments()
        self.state_changed.emit()
        return True

    def set_assignment_audio(self, monitor_key: str, muted: bool, volume: int) -> bool:
        assignment = self._assignments.get(monitor_key)
        if assignment is None:
            return False
        assignment.muted = bool(muted)
        assignment.volume = max(0, min(100, int(volume)))
        window = self._windows.get(monitor_key)
        if window is not None:
            window.view.set_muted(assignment.muted)
            window.view.set_volume(assignment.volume)
        self._save_assignments()
        self.state_changed.emit()
        return True

    def set_assignment_fit(self, monitor_key: str, fit: str) -> bool:
        """Change the display mode only for one monitor's assignment."""
        if fit not in FIT_MODES:
            return False
        assignment = self._assignments.get(monitor_key)
        if assignment is None:
            return False
        item = self.db.get_media(assignment.media_id) if assignment.media_id else None
        monitor = self.monitors.get(monitor_key)
        if item is not None and monitor is not None:
            self._apply_one(monitor, item, fit_override=fit)
            updated = self._assignments.get(monitor_key)
            if updated is not None:
                updated.fit = fit
                updated.fit_explicit = True
        else:
            assignment.fit = fit
            assignment.fit_explicit = True
            window = self._windows.get(monitor_key)
            if window is not None:
                window.view.set_fit(fit)
        self._save_assignments()
        self.state_changed.emit()
        return True

    def set_media_fit(self, media_id: int, fit: str) -> bool:
        """Set the default display mode for a wallpaper (all non-overridden monitors)."""
        if fit not in FIT_MODES:
            return False
        item = self.db.get_media(media_id)
        if item is None:
            return False
        meta = dict(item.meta or {})
        meta["fit"] = fit
        item.meta = meta
        self.db.upsert_media(item)
        for key, assignment in list(self._assignments.items()):
            if assignment.media_id != media_id or assignment.fit_explicit:
                continue
            monitor = self.monitors.get(key)
            if monitor is None:
                continue
            self._apply_one(monitor, item, fit_override=fit)
            updated = self._assignments.get(key)
            if updated is not None:
                updated.fit = fit
                updated.fit_explicit = False
        self._save_assignments()
        self.state_changed.emit()
        return True

    def _set_static(self, monitor: MonitorInfo, path: str) -> bool:
        try:
            if system_wallpaper.set_static_wallpaper_monitor(monitor, path):
                return True
            if len(self.monitors.monitors()) <= 1:
                return system_wallpaper.set_static_wallpaper_all(path)
        except Exception:  # noqa: BLE001
            log.exception("static wallpaper failed")
        return False

    def set_monitor_enabled(self, monitor_key: str, enabled: bool) -> None:
        assignment = self._assignments.get(monitor_key)
        if assignment is None:
            return
        assignment.enabled = bool(enabled)
        window = self._windows.get(monitor_key)
        if window is not None:
            window.view.set_paused(self._should_pause(monitor_key))
        self._save_assignments()
        self.state_changed.emit()

    def remove(self, monitor_key: str) -> None:
        self._destroy_window(monitor_key)
        assignment = self._assignments.pop(monitor_key, None)
        if assignment is not None:
            monitor = self.monitors.get(monitor_key)
            if monitor is not None and assignment.kind == "image":
                system_wallpaper.restore_wallpaper(
                    monitor, self._previous_wallpapers.get(monitor_key))
            self._save_assignments()
        self.state_changed.emit()

    def pause(self) -> None:
        if not self._user_paused:
            self._user_paused = True
            self._apply_pause_to_views()
            self.state_changed.emit()

    def resume(self) -> None:
        """Resume every monitor (clears both global and per-monitor pauses)."""
        changed = bool(self._user_paused) or any(
            assignment.paused for assignment in self._assignments.values())
        if changed:
            self._user_paused = False
            for assignment in self._assignments.values():
                assignment.paused = False
            self._apply_pause_to_views()
            self._save_assignments()
            self.state_changed.emit()

    def monitor_paused(self, monitor_key: str) -> bool:
        assignment = self._assignments.get(monitor_key)
        return bool(self._user_paused or (assignment is not None and assignment.paused))

    def set_monitor_paused(self, monitor_key: str, paused: bool) -> None:
        assignment = self._assignments.get(monitor_key)
        if assignment is None:
            return
        if paused:
            if not assignment.paused:
                assignment.paused = True
                self._apply_pause_to_views()
                self._save_assignments()
                self.state_changed.emit()
            return
        if self._user_paused:
            # Split a global pause into per-monitor pauses, then resume this one.
            self._user_paused = False
            for key, other in self._assignments.items():
                other.paused = key != monitor_key
        assignment.paused = False
        self._apply_pause_to_views()
        self._save_assignments()
        self.state_changed.emit()

    def toggle_monitor_paused(self, monitor_key: str) -> bool:
        target = not self.monitor_paused(monitor_key)
        self.set_monitor_paused(monitor_key, target)
        return target

    def set_paused(self, paused: bool) -> None:
        if paused:
            self.pause()
        else:
            self.resume()

    def toggle_paused(self) -> bool:
        self.set_paused(not self._user_paused)
        return self._user_paused

    # ----------------------------------------------------------------- settings
    def set_mode(self, mode: str) -> None:
        if mode not in PERFORMANCE_MODES:
            return
        self._mode = mode
        self.settings.set("performance.mode", mode)
        self.set_fps_cap(int(PERFORMANCE_MODES[mode]["fps"]), persist=False)

    def set_fps_cap(self, fps: int, persist: bool = True) -> None:
        self._fps_cap = max(1, min(240, int(fps)))
        self._apply_quality()
        if persist:
            self.settings.set("performance.fps_cap", self._fps_cap)
        self.state_changed.emit()

    def set_fit(self, fit: str) -> None:
        if fit not in FIT_MODES:
            return
        self.settings.set("playback.fit", fit)
        for key, assignment in list(self._assignments.items()):
            if assignment.fit_explicit:
                continue
            assignment.fit = fit
            window = self._windows.get(key)
            if window is not None:
                window.view.set_fit(fit)
        self._save_assignments()
        self.state_changed.emit()

    def set_muted(self, muted: bool) -> None:
        for window in self._windows.values():
            window.view.set_muted(muted)
        self.settings.set("playback.muted", muted)

    def set_volume(self, volume: int) -> None:
        for window in self._windows.values():
            window.view.set_volume(volume)
        self.settings.set("playback.volume", volume)

    def set_speed(self, speed: float) -> None:
        for window in self._windows.values():
            window.view.set_speed(speed)
        self.settings.set("playback.speed", speed)

    def set_loop(self, loop: bool) -> None:
        for window in self._windows.values():
            window.view.set_loop(loop)
        self.settings.set("playback.loop", bool(loop))

    # ------------------------------------------------------------------- windows
    def refresh(self) -> None:
        if not bool(self.settings.get("general.restore_wallpapers", True)):
            return
        monitors = self.monitors.monitors()
        monitor_map = {monitor.key: monitor for monitor in monitors}
        for key in list(self._windows.keys()):
            if key not in monitor_map:
                self._destroy_window(key)
        for key, assignment in list(self._assignments.items()):
            monitor = monitor_map.get(key)
            if monitor is None:
                continue
            if not assignment.file_path or not os.path.exists(assignment.file_path):
                log.warning("wallpaper file missing: %s", assignment.file_path)
                self._destroy_window(key)
                continue
            if assignment.kind == "image" and self._set_static(monitor, assignment.file_path):
                # Static pictures are normal Windows wallpapers - no desktop window.
                self._destroy_window(key)
                continue
            window = self._windows.get(key)
            if window is None:
                window = self._ensure_window(monitor)
                if window is None:
                    continue
                source = self._source_for(assignment)
                window.view.set_source(
                    source, assignment.kind,
                    fit=assignment.fit, muted=assignment.muted,
                    volume=assignment.volume, speed=assignment.speed,
                    fps_cap=self._fps_for(assignment),
                    loop=bool(self.settings.get("playback.loop", True)))
                window.view.set_render_scale(self._render_scale)
                self._view_sources[key] = source
            else:
                window.update_geometry(monitor, self.monitors.screen_for(monitor))
            if not window.attached:
                self._attach_window(window)
            self._assignments[key] = assignment
        if not self.adaptive_enabled:
            self.apply_quality_mode()
        self.state_changed.emit()

    def _ensure_window(self, monitor: MonitorInfo) -> DesktopWindow | None:
        window = self._windows.get(monitor.key)
        if window is not None:
            return window
        screen = self.monitors.screen_for(monitor)
        try:
            window = DesktopWindow(monitor, screen)
        except Exception:  # noqa: BLE001
            log.exception("could not create desktop window")
            return None
        self._windows[monitor.key] = window
        self._attach_window(window)
        return window

    def _attach_window(self, window: DesktopWindow) -> bool:
        self._find_workerw()
        attached = window.attach(self._workerw)
        if not attached:
            if self._attach_warned < MAX_RETRY_LOG:
                log.warning("could not attach wallpaper window to the desktop layer "
                            "(WorkerW=0x%X) - will retry", self._workerw)
                self._attach_warned += 1
            self.error.emit("Could not attach to the desktop layer. "
                            "Restart Explorer or the application.")
        else:
            self._attach_warned = 0
        return attached

    def _destroy_window(self, monitor_key: str) -> None:
        window = self._windows.pop(monitor_key, None)
        if window is not None:
            window.destroy()

    def _find_workerw(self) -> int:
        if not self._workerw or not winapi.user32.IsWindow(self._workerw):
            self._workerw = winapi.find_wallpaper_workerw()
        return self._workerw

    # -------------------------------------------------------------------- pause
    def _should_pause(self, monitor_key: str) -> bool:
        assignment = self._assignments.get(monitor_key)
        if assignment is not None and not assignment.enabled:
            return True
        if self._user_paused:
            return True
        if assignment is not None and assignment.paused:
            return True
        state = self._pause_state
        if state.idle and bool(self.settings.get("performance.pause_when_idle", True)):
            return True
        if state.on_battery and bool(self.settings.get("performance.pause_on_battery", True)):
            return True
        if (bool(self.settings.get("performance.pause_on_fullscreen", True))
                and monitor_key in state.fullscreen_monitors):
            return True
        return False

    def _apply_pause_to_views(self) -> None:
        for key, window in self._windows.items():
            window.view.set_paused(self._should_pause(key))

    def _tick(self) -> None:
        if not self._windows:
            return
        monitors = self.monitors.monitors()
        state = self._detector.poll(monitors)
        self._pause_state = state
        self._auto_paused = bool(
            (state.idle and bool(self.settings.get("performance.pause_when_idle", True)))
            or (state.on_battery and bool(self.settings.get("performance.pause_on_battery", True)))
            or (state.fullscreen_monitors
                and bool(self.settings.get("performance.pause_on_fullscreen", True)))
        )
        signature = (frozenset(state.fullscreen_monitors), state.idle, state.on_battery,
                     self._user_paused)
        if signature != self._last_pause_signature:
            self._last_pause_signature = signature
            self._apply_pause_to_views()
            self.state_changed.emit()
        # Re-attach windows that lost their parent (e.g. Explorer restarted).
        self._find_workerw()
        for window in self._windows.values():
            if not window.attached or not winapi.user32.IsWindow(window.native_handle()):
                self._attach_window(window)
            elif winapi.user32.GetAncestor(window.native_handle(), winapi.GA_PARENT) != self._workerw:
                self._attach_window(window)

    def detector_poll(self, monitors: list[MonitorInfo]) -> PauseState:
        return self._detector.poll(monitors)

    # ---------------------------------------------------------------- settings io
    def _load_assignments(self) -> None:
        raw = self.settings.get("monitors.assignments", {}) or {}
        for monitor_key, data in raw.items():
            if not isinstance(data, dict):
                continue
            assignment = Assignment.from_dict(monitor_key, data)
            if assignment.file_path and os.path.exists(assignment.file_path):
                self._assignments[monitor_key] = assignment
            else:
                log.warning("stored wallpaper file is missing: %s", assignment.file_path)

    def _save_assignments(self) -> None:
        self.settings.set("monitors.assignments",
                          {key: value.to_dict() for key, value in self._assignments.items()})

    def _capture_previous_wallpapers(self) -> None:
        try:
            for monitor in self.monitors.monitors():
                self._previous_wallpapers[monitor.key] = system_wallpaper.get_previous_wallpaper(
                    monitor)
        except Exception:  # noqa: BLE001
            log.exception("could not read previous wallpapers")

    # ------------------------------------------------------------------ cleanup
    def shutdown(self) -> None:
        self._timer.stop()
        for key in list(self._windows.keys()):
            self._destroy_window(key)
        try:
            self._save_assignments()
        except Exception:  # noqa: BLE001
            pass

