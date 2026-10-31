"""Application settings: JSON file with dotted-key access and listeners."""
from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from typing import Any, Callable

from config import paths

DEFAULTS: dict[str, Any] = {
    "general": {
        "run_at_startup": False,
        "start_minimized": False,
        "close_to_tray": True,
        "language": "ru",
        "check_updates": False,
        "restore_wallpapers": True,
    },
    "appearance": {
        "theme": "aurora",
        "accent": "purple",
        "aurora_accent": "purple",
        "classic_accent": "yellow",
        "ui_scale": 100,
        "animations": True,
        "compact": False,
    },
    "performance": {
        "mode": "balanced",
        "fps_cap": 30,
        "adaptive_quality": True,
        "hardware_decoding": True,
        "auto_pause": True,
        "pause_on_fullscreen": True,
        "pause_when_idle": True,
        "idle_minutes": 5,
        "pause_on_battery": True,
        "resource_limits": True,
    },
    "playback": {
        "volume": 0,
        "muted": True,
        "loop": True,
        "fit": "cover",
        "quality": "auto",
        "manual_quality": "original",
        "speed": 1.0,
    },
    "storage": {
        "library_dir": str(paths.DEFAULT_LIBRARY_DIR),
        "download_dir": str(paths.DEFAULT_DOWNLOAD_DIR),
        "cache_limit_mb": 2048,
        "clear_thumbs_on_exit": False,
        "keep_original_files": True,
    },
    "import": {
        "use_ytdlp": True,
        "max_height": 1080,
        "auto_optimize": True,
        "prefer_optimized": True,
        "last_url": "",
    },
    "providers": {
        "pixabay_key": "",
        "pexels_key": "",
        "pixabay_enabled": True,
        "pexels_enabled": True,
        "search_cache_minutes": 30,
    },
    "monitors": {
        "assignments": {},
    },
    "window": {
        "width": 1380,
        "height": 860,
        "sidebar_collapsed": False,
    },
    "downloads": {
        "concurrent": 2,
    },
}


def _deep_merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Settings:
    """Thread-safe settings store backed by a JSON file.

    Access values with dotted paths: ``settings.get("performance.fps_cap")``.
    Listeners are called with the dotted key that changed.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else paths.SETTINGS_FILE
        self._lock = threading.RLock()
        self._listeners: list[Callable[[str], None]] = []
        self._data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    # -- io ------------------------------------------------------------------
    def load(self) -> None:
        with self._lock:
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = _deep_merge(DEFAULTS, raw)
            except (OSError, ValueError):
                self._data = copy.deepcopy(DEFAULTS)

    def save(self) -> None:
        with self._lock:
            data = copy.deepcopy(self._data)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except OSError:
            pass

    # -- access --------------------------------------------------------------
    @property
    def data(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            node: Any = self._data
            for part in key.split("."):
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return copy.deepcopy(node)

    def set(self, key: str, value: Any, save: bool = True) -> None:
        parts = key.split(".")
        with self._lock:
            node = self._data
            for part in parts[:-1]:
                if not isinstance(node.get(part), dict):
                    node[part] = {}
                node = node[part]
            if node.get(parts[-1]) == value:
                return
            node[parts[-1]] = value
        if save:
            self.save()
        self._notify(key)

    def update(self, patch: dict[str, Any], save: bool = True) -> None:
        with self._lock:
            self._data = _deep_merge(self._data, patch)
        if save:
            self.save()
        self._notify("")

    # -- listeners -----------------------------------------------------------
    def add_listener(self, callback: Callable[[str], None]) -> None:
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[str], None]) -> None:
        with self._lock:
            try:
                self._listeners.remove(callback)
            except ValueError:
                pass

    def _notify(self, key: str) -> None:
        for callback in list(self._listeners):
            try:
                callback(key)
            except Exception:  # noqa: BLE001 - a broken listener must not break settings
                pass

    # -- helpers -------------------------------------------------------------
    def api_key(self, provider: str) -> str:
        return str(self.get(f"providers.{provider}_key", "") or "").strip()

    def assignments(self) -> dict[str, Any]:
        return dict(self.get("monitors.assignments", {}) or {})

    def set_assignment(self, monitor_key: str, assignment: dict | None) -> None:
        assignments = self.assignments()
        if assignment:
            assignments[monitor_key] = assignment
        else:
            assignments.pop(monitor_key, None)
        self.set("monitors.assignments", assignments)

