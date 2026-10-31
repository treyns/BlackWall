"""High-level orchestration of a TikTok/YouTube/Pinterest link import."""
from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from config import paths
from core import utils
from core.database import now_iso
from core.logger import get_logger
from core.models import MediaItem
from importers.base import (
    ImportCancelled,
    ImportError,
    ImportLink,
    LinkInfo,
    detect_link,
    friendly_download_error,
    safe_filename,
    ytdlp_available,
)
from importers.processing import (
    ensure_playable_video,
    free_space_ok,
    make_thumbnail,
    needs_optimization,
    optimized_path_for,
    probe_video,
    target_dimensions,
)
from importers.pinterest import PinterestProvider
from importers.tiktok import TikTokProvider
from importers.youtube import YouTubeProvider

log = get_logger("importers.manager")

MIN_FREE_BYTES = 256 * 1024 * 1024


class ImportManager(QObject):
    info_ready = Signal(object)        # LinkInfo
    info_failed = Signal(str)          # user-facing English message key
    started = Signal()
    phase = Signal(str)                # English phase key
    progress = Signal(int, str)        # percent, text key
    finished = Signal(int, bool)       # media_id, already existed
    failed = Signal(str)               # user-facing message
    cancelled = Signal()

    def __init__(self, db, settings, library, monitors, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.settings = settings
        self.library = library
        self.monitors = monitors
        self._providers = {
            "youtube": YouTubeProvider(),
            "tiktok": TikTokProvider(),
            "pinterest": PinterestProvider(),
        }
        self._cancel = threading.Event()
        self._busy = False
        self._lock = threading.Lock()
        self.last_info: LinkInfo | None = None

    # ---------------------------------------------------------------- helpers
    def provider_for(self, url: str):
        link = detect_link(url)
        if link is None:
            return None
        return self._providers.get(link.source)

    def parse(self, url: str) -> ImportLink | None:
        return detect_link(url)

    def max_height(self) -> int:
        return int(self.settings.get("import.max_height", 1080) or 1080)

    @property
    def busy(self) -> bool:
        return self._busy

    def ytdlp_available(self) -> bool:
        return ytdlp_available()

    # ----------------------------------------------------------------- metadata
    def fetch_info(self, url: str) -> None:
        if self._busy:
            self.info_failed.emit("Another import is already running")
            return
        provider = self.provider_for(url)
        if provider is None:
            self.info_failed.emit("Paste a link to a TikTok, YouTube or Pinterest video")
            return
        with self._lock:
            if self._busy:
                self.info_failed.emit("Another import is already running")
                return
            self._busy = True
        self._cancel.clear()
        thread = threading.Thread(target=self._fetch_worker, args=(url, provider),
                                  daemon=True, name="import-metadata")
        thread.start()

    def _fetch_worker(self, url: str, provider) -> None:
        try:
            provider.max_height = self.max_height()
            info = provider.fetch_info(url)
            info.thumbnail_path = self._cache_thumbnail(info)
            self.last_info = info
            self.info_ready.emit(info)
        except ImportError as error:
            log.warning("metadata error: %s (%s)", error.message, error.detail)
            self.info_failed.emit(error.message)
        except Exception as error:  # noqa: BLE001
            log.exception("metadata failed")
            self.info_failed.emit(friendly_download_error(error).message)
        finally:
            with self._lock:
                self._busy = False

    def _cache_thumbnail(self, info: LinkInfo) -> str:
        if not info.thumbnail_url:
            return ""
        try:
            import requests

            paths.REMOTE_THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
            suffix = Path(info.thumbnail_url.split("?", 1)[0]).suffix or ".jpg"
            target = paths.REMOTE_THUMBNAILS_DIR / f"import_{info.source}_{info.video_id}{suffix}"
            if target.exists() and target.stat().st_size > 0:
                return str(target)
            response = requests.get(info.thumbnail_url, timeout=20)
            response.raise_for_status()
            target.write_bytes(response.content)
            return str(target)
        except Exception as error:  # noqa: BLE001
            log.warning("thumbnail download failed: %s", error)
            return ""

    # ------------------------------------------------------------------ import
    def start_import(self, url: str, info: LinkInfo | None = None) -> None:
        if not ytdlp_available():
            self.failed.emit("yt-dlp is not installed; install it with pip")
            return
        provider = self.provider_for(url)
        if provider is None:
            self.failed.emit("Paste a link to a TikTok, YouTube or Pinterest video")
            return
        with self._lock:
            if self._busy:
                self.failed.emit("Another import is already running")
                return
            self._busy = True
        self._cancel.clear()
        self.started.emit()
        thread = threading.Thread(target=self._import_worker,
                                  args=(url, provider, info), daemon=True,
                                  name="import-video")
        thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    # -------------------------------------------------------------- reprocess
    def import_local_file(self, path: str) -> None:
        if not os.path.isfile(path):
            self.failed.emit("The selected file is not a supported video")
            return
        with self._lock:
            if self._busy:
                self.failed.emit("Another import is already running")
                return
            self._busy = True
        self._cancel.clear()
        self.started.emit()
        threading.Thread(target=self._local_worker, args=(str(path),),
                         daemon=True, name="import-local-video").start()

    def _local_worker(self, path: str) -> None:
        try:
            from core.database import path_id
            from importers.base import is_playable_video

            if not is_playable_video(path):
                raise ImportError("The selected file is not a supported video", "format")
            self.phase.emit("Checking the video…")
            playable = ensure_playable_video(
                path, progress=lambda pct: self.progress.emit(pct, "Checking the video…"))
            self.phase.emit("Preparing video…")
            existing = self.db.find_by_file(path)
            if existing is not None and existing.file_path and os.path.exists(existing.file_path):
                self.finished.emit(int(existing.id or 0), True)
                return
            probe = probe_video(playable)
            if not probe.get("width") or not probe.get("height"):
                raise ImportError("The downloaded file is not a readable video", "probe")
            if not free_space_ok(int(os.path.getsize(playable) * 2) + 64 * 1024 * 1024):
                raise ImportError("Not enough free disk space", "disk")
            imported_at = now_iso()
            aspect = probe.get("aspect", "")
            size = os.path.getsize(playable)
            title = Path(path).stem
            thumb = make_thumbnail(playable, str(paths.THUMBNAILS_DIR /
                                                 f"local_{path_id(path)[:16]}.jpg"),
                                   position=min(1.0, float(probe.get("duration") or 1.0) / 2))
            item = MediaItem(
                title=title, source="local", source_id=path_id(path),
                file_path=playable, original_path=path, page_url="", thumb_path=thumb or "",
                width=int(probe.get("width") or 0), height=int(probe.get("height") or 0),
                duration=float(probe.get("duration") or 0.0),
                format=Path(playable).suffix.lstrip(".").upper(), size_bytes=size,
                imported_at=imported_at, aspect=aspect, added_at=imported_at,
                meta={"fps": float(probe.get("fps") or 0.0), "aspect": aspect,
                      "imported_at": imported_at, "original_path": path, "fit": "cover"},
            )
            media_id = self.db.upsert_media(item)
            self.library.changed.emit()
            optimized: str | None = None
            target_w, target_h = target_dimensions(item.width, item.height,
                                                   self.monitors.monitors())
            if (bool(self.settings.get("import.auto_optimize", True))
                    and needs_optimization(probe, target_w, target_h)):
                destination = optimized_path_for(playable, media_id, target_w)
                self.phase.emit("Creating optimized copy…")
                self.progress.emit(0, "Creating optimized copy…")

                def on_progress(percent: int) -> None:
                    self.progress.emit(percent, "Creating optimized copy…")

                optimized = self._optimize(playable, destination, target_w, target_h,
                                           probe, on_progress)
                self.db.update_import_info(media_id, optimized_path=optimized)
                item.optimized_path = optimized
                item.meta["optimized_path"] = optimized
                self.db.upsert_media(item)
                self.library.changed.emit()
            self.phase.emit("Adding to library…")
            self.progress.emit(100, "Done")
            log.info("local video imported: %s -> media #%s", path, media_id)
            self.finished.emit(int(media_id), False)
        except ImportCancelled:
            self.cancelled.emit()
        except ImportError as error:
            self.failed.emit(error.message)
        except Exception as error:  # noqa: BLE001
            log.exception("local import failed")
            self.failed.emit(friendly_download_error(error).message)
        finally:
            with self._lock:
                self._busy = False

        with self._lock:
            if self._busy:
                self.failed.emit("Another import is already running")
                return
            self._busy = True
        self._cancel.clear()
        self.started.emit()
        threading.Thread(target=self._reprocess_worker, args=(int(media_id),),
                         daemon=True, name="reprocess-video").start()

    def reprocess(self, media_id: int) -> None:
        with self._lock:
            if self._busy:
                self.failed.emit("Another import is already running")
                return
            self._busy = True
        self._cancel.clear()
        self.started.emit()
        threading.Thread(target=self._reprocess_worker, args=(int(media_id),),
                         daemon=True, name="reprocess-video").start()

    def _reprocess_worker(self, media_id: int) -> None:
        try:
            item = self.db.get_media(media_id)
            if item is None:
                raise ImportError("This video is no longer in the library", "missing")
            source = item.original_path or item.file_path
            if not source or not os.path.exists(source):
                raise ImportError("The original video file is missing", "missing")
            self.phase.emit("Preparing video…")
            probe = probe_video(source)
            target_w, target_h = target_dimensions(
                int(probe.get("width") or item.width),
                int(probe.get("height") or item.height),
                self.monitors.monitors())
            destination = optimized_path_for(source, media_id, target_w)
            self.phase.emit("Creating optimized copy…")
            self.progress.emit(0, "Creating optimized copy…")

            def on_progress(percent: int) -> None:
                self.progress.emit(percent, "Creating optimized copy…")

            optimized = self._optimize(source, destination, target_w, target_h,
                                       probe, on_progress)
            self.db.update_import_info(media_id, optimized_path=optimized)
            updated = self.db.get_media(media_id)
            if updated is not None:
                meta = dict(updated.meta or {})
                meta["optimized_path"] = optimized
                updated.meta = meta
                updated.optimized_path = optimized
                self.db.upsert_media(updated)
            self.library.changed.emit()
            self.progress.emit(100, "Done")
            log.info("reprocessed media #%s -> %s", media_id, optimized)
            self.finished.emit(media_id, True)
        except ImportCancelled:
            self.cancelled.emit()
        except ImportError as error:
            self.failed.emit(error.message)
        except Exception as error:  # noqa: BLE001
            log.exception("reprocess failed")
            self.failed.emit(friendly_download_error(error).message)
        finally:
            with self._lock:
                self._busy = False

    def _import_worker(self, url: str, provider, cached_info: LinkInfo | None) -> None:
        temp_dir = paths.IMPORTS_DIR / "_tmp"
        media_id: int | None = None
        try:
            provider.max_height = self.max_height()
            self.phase.emit("Fetching video information…")
            info = cached_info or provider.fetch_info(url)
            if self._cancel.is_set():
                raise ImportCancelled("cancelled")

            existing = (self.db.get_by_source(provider.key, info.video_id)
                        if info.video_id else None)
            if existing is not None and existing.file_path and os.path.exists(existing.file_path):
                log.info("import skipped, already in library: %s", info.video_id)
                self.finished.emit(int(existing.id or 0), True)
                return

            if not free_space_ok(MIN_FREE_BYTES):
                raise ImportError("Not enough free disk space", "disk")

            estimated = int(info.filesize or 0)
            needed = max(MIN_FREE_BYTES, estimated * 2 + 64 * 1024 * 1024) if estimated else MIN_FREE_BYTES
            if not free_space_ok(needed):
                raise ImportError("Not enough free disk space", "disk")

            job_dir = temp_dir / f"{provider.key}_{info.video_id or 'video'}"
            shutil.rmtree(job_dir, ignore_errors=True)
            job_dir.mkdir(parents=True, exist_ok=True)
            self.phase.emit("Downloading video…")

            def on_download(data: dict) -> None:
                if self._cancel.is_set():
                    raise ImportCancelled("cancelled")
                status = data.get("status")
                if status == "downloading":
                    total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                    downloaded = data.get("downloaded_bytes") or 0
                    percent = int(downloaded / total * 100) if total else 0
                    self.progress.emit(max(0, min(100, percent)), "Downloading video…")
                elif status == "finished":
                    self.progress.emit(100, "Download complete, preparing video…")

            path, _data = provider.download(url, job_dir, max_height=self.max_height(),
                                            progress=on_download, cancel=self._cancel)
            if self._cancel.is_set():
                raise ImportCancelled("cancelled")
            self.phase.emit("Checking the video…")
            path = ensure_playable_video(
                path, progress=lambda pct: self.progress.emit(pct, "Checking the video…"))

            probe = probe_video(path)
            if not probe.get("width") or not probe.get("height"):
                raise ImportError("The downloaded file is not a readable video", "probe")
            if not free_space_ok(int(os.path.getsize(path) * 2) + 64 * 1024 * 1024):
                raise ImportError("Not enough free disk space", "disk")

            final_path = self._move_to_imports(path, provider.key, info)
            size = os.path.getsize(final_path)
            thumb = make_thumbnail(final_path,
                                   str(paths.THUMBNAILS_DIR /
                                       f"import_{provider.key}_{info.video_id or 'video'}.jpg"),
                                   position=min(1.0, float(probe.get("duration") or 1.0) / 2))
            imported_at = now_iso()
            aspect = probe.get("aspect", "")
            item = MediaItem(
                title=info.title or Path(final_path).stem,
                source=provider.key,
                source_id=info.video_id or Path(final_path).stem,
                file_path=final_path,
                original_path=final_path,
                page_url=info.webpage_url or url,
                thumb_path=thumb or "",
                width=int(probe.get("width") or info.width or 0),
                height=int(probe.get("height") or info.height or 0),
                duration=float(probe.get("duration") or info.duration or 0.0),
                format=Path(final_path).suffix.lstrip(".").upper(),
                size_bytes=size,
                imported_at=imported_at,
                author=info.author,
                aspect=aspect,
                added_at=imported_at,
                meta={
                    "fps": float(probe.get("fps") or info.fps or 0.0),
                    "aspect": aspect,
                    "author": info.author,
                    "source_label": provider.label,
                    "source_url": info.webpage_url or url,
                    "imported_at": imported_at,
                    "original_path": final_path,
                    "fit": "cover",
                },
            )
            media_id = self.db.upsert_media(item)
            self.library.changed.emit()

            optimized: str | None = None
            auto_optimize = bool(self.settings.get("import.auto_optimize", True))
            target_w, target_h = target_dimensions(item.width, item.height,
                                                   self.monitors.monitors())
            if auto_optimize and needs_optimization(probe, target_w, target_h):
                if not free_space_ok(int(size * 1.5) + 64 * 1024 * 1024):
                    self.progress.emit(100, "Not enough free space for optimization")
                else:
                    self.phase.emit("Creating optimized copy…")
                    destination = optimized_path_for(final_path, media_id, target_w)
                    self.progress.emit(0, "Creating optimized copy…")

                    def on_optimize(percent: int) -> None:
                        self.progress.emit(percent, "Creating optimized copy…")

                    try:
                        optimized = self._optimize(final_path, destination, target_w,
                                                   target_h, probe, on_optimize)
                    except ImportError as error:
                        log.warning("optimization skipped: %s", error.message)
                    if optimized:
                        item.optimized_path = optimized
                        item.meta["optimized_path"] = optimized
                        self.db.update_import_info(media_id, optimized_path=optimized)
                        self.db.upsert_media(item)
                        self.library.changed.emit()

            self.phase.emit("Adding to library…")
            log.info("imported %s %s -> media #%s", provider.key, info.video_id, media_id)
            self.progress.emit(100, "Imported")
            self.finished.emit(int(media_id), False)
        except ImportCancelled:
            log.info("import cancelled")
            self.cancelled.emit()
        except ImportError as error:
            log.warning("import error: %s (%s)", error.message, error.detail)
            self.failed.emit(error.message)
        except Exception as error:  # noqa: BLE001
            log.exception("import failed")
            self.failed.emit(friendly_download_error(error).message)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            with self._lock:
                self._busy = False

    def _optimize(self, path: str, destination: str, target_w: int, target_h: int,
                  probe: dict, progress) -> str:
        from importers.processing import optimize_video

        return optimize_video(
            path, destination, target_w, target_h,
            source_fps=float(probe.get("fps") or 0.0),
            duration=float(probe.get("duration") or 0.0),
            progress=progress, cancel=self._cancel)

    def _move_to_imports(self, path: str, source: str, info: LinkInfo) -> str:
        folder = paths.IMPORTS_DIR / source
        folder.mkdir(parents=True, exist_ok=True)
        ext = Path(path).suffix.lower() or ".mp4"
        base = safe_filename(f"{info.title}_{info.video_id}", f"{source}_{info.video_id or 'video'}")
        target = folder / f"{base}{ext}"
        if target.exists():
            target = folder / f"{base}_{now_iso().replace(':', '-').replace(' ', '_')}{ext}"
        shutil.move(str(path), str(target))
        return str(target)

