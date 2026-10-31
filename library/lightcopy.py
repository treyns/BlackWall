"""Generation of lightweight video copies for adaptive / manual video quality.

An MP4 file has a fixed resolution, so "lower resolution playback" needs a
prepared copy. BlackWall creates one on demand with the FFmpeg build shipped by
``imageio-ffmpeg`` and caches it in ``cache/optimized``.  Every target width gets
its own cached file, so the user can switch between Original / 1080p / 720p /
480p without re-encoding the same file again.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from core.logger import get_logger

log = get_logger("optimizer")

# Manual quality presets (target video width in pixels).
QUALITY_WIDTHS = {
    "1080p": 1920,
    "720p": 1280,
    "480p": 854,
}
ADAPTIVE_WIDTH = 1280  # the automatically chosen lightweight copy
TARGET_CRF = 23


def _source_id(path: str) -> str:
    return hashlib.sha1(os.path.normcase(os.path.abspath(path)).encode("utf-8")).hexdigest()[:16]


def _ffmpeg_executable() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


class LightCopyManager(QObject):
    ready = Signal(str, str, int)    # original path, light copy path, target width
    failed = Signal(str, str, int)    # original path, error, target width

    def __init__(self, cache_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache_dir = Path(cache_dir)
        self._lock = threading.RLock()
        self._pending: set[tuple[str, int]] = set()
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------ lookup
    def _target_file(self, source: str, width: int) -> Path:
        # The suffix marks audio-preserving copies; older silent files are not
        # reused so a wallpaper with music never loses its soundtrack silently.
        return self._cache_dir / f"{_source_id(source)}_{int(width)}_a.mp4"

    def path_for(self, source: str, max_width: int = ADAPTIVE_WIDTH) -> str | None:
        if not source:
            return None
        target = self._target_file(source, max_width)
        return str(target) if target.exists() else None

    def is_pending(self, source: str, max_width: int = ADAPTIVE_WIDTH) -> bool:
        with self._lock:
            return (source, int(max_width)) in self._pending

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    # ------------------------------------------------------------------ create
    def request(self, source: str, max_width: int = ADAPTIVE_WIDTH) -> None:
        if not source or not os.path.exists(source):
            return
        max_width = int(max_width)
        existing = self.path_for(source, max_width)
        if existing is not None:
            self.ready.emit(source, existing, max_width)
            return
        with self._lock:
            if (source, max_width) in self._pending:
                return
            self._pending.add((source, max_width))
        thread = threading.Thread(target=self._generate, args=(source, max_width),
                                  daemon=True, name="light-copy")
        thread.start()

    def _generate(self, source: str, max_width: int) -> None:
        ffmpeg = _ffmpeg_executable()
        try:
            if not ffmpeg:
                raise RuntimeError("FFmpeg executable is not available")
            target = self._target_file(source, max_width)
            tmp_file = target.with_suffix(".part.mp4")
            filter_scale = f"scale='min({max_width},iw)':-2"
            command = [
                ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-i", source,
                "-map", "0:v:0", "-map", "0:a?",
                "-vf", filter_scale,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", str(TARGET_CRF),
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                str(tmp_file),
            ]
            log.info("creating lightweight copy (%spx): %s", max_width, source)
            process = subprocess.run(command, capture_output=True, text=True,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if process.returncode != 0:
                raise RuntimeError((process.stderr or "ffmpeg failed").strip()[:300])
            if not tmp_file.exists() or tmp_file.stat().st_size == 0:
                raise RuntimeError("the lightweight copy is empty")
            tmp_file.replace(target)
            log.info("lightweight copy ready: %s", target)
            self.ready.emit(source, str(target), int(max_width))
        except Exception as error:  # noqa: BLE001
            log.warning("lightweight copy failed for %s: %s", source, error)
            self.failed.emit(source, str(error), int(max_width))
        finally:
            with self._lock:
                self._pending.discard((source, int(max_width)))

    def clear(self) -> None:
        try:
            for file in self._cache_dir.glob("*.mp4"):
                file.unlink()
        except OSError:
            pass

