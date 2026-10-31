"""Library manager: importing local files, favourites and metadata."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from config import paths
from core import utils
from core.database import Database, path_id
from core.models import MediaItem, SearchResult
from core.logger import get_logger

log = get_logger("library")


class LibraryManager(QObject):
    changed = Signal()

    def __init__(self, db: Database, settings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.settings = settings
        # Filled by :meth:`import_files` so the UI can report real numbers.
        self.last_import_summary: dict[str, int] = {"added": 0, "existing": 0, "failed": 0}

    # ------------------------------------------------------------------ listing
    def list_items(self, search: str = "", sort: str = "added", kind: str = "all",
                   favorites_only: bool = False) -> list[MediaItem]:
        return self.db.list_library(search=search, sort=sort, kind=kind,
                                    favorites_only=favorites_only)

    def favorites(self, search: str = "", sort: str = "added") -> list[MediaItem]:
        return self.db.list_favorites(search=search, sort=sort)

    def recent(self, limit: int = 6) -> list[MediaItem]:
        return self.db.recent(limit)

    def get(self, media_id: int) -> MediaItem | None:
        return self.db.get_media(media_id)

    def stats(self) -> dict[str, int]:
        return self.db.stats()

    # ------------------------------------------------------------------ import
    def import_files(self, file_paths: list[str]) -> tuple[list[int], list[str]]:
        """Register existing files in the library. Files are never copied/moved."""
        imported: list[int] = []
        errors: list[str] = []
        added = existing = 0
        for raw in file_paths:
            try:
                path = os.path.abspath(str(raw))
                if not os.path.isfile(path):
                    errors.append(f"{os.path.basename(str(raw))}: file not found")
                    continue
                if not utils.is_playable(path):
                    errors.append(f"{os.path.basename(path)}: unsupported format")
                    continue
                # Look the row up by its stable file id (same file, different case or
                # separators must not create a duplicate).
                current = self.db.get_by_source("local", path_id(path))
                if current is None:
                    current = self.db.find_by_file(path)
                if current is not None and current.id is not None:
                    imported.append(current.id)
                    existing += 1
                    continue
                info = utils.probe_media(path)
                if info["kind"] == "video" and not info["width"]:
                    errors.append(f"{os.path.basename(path)}: cannot read video")
                    continue
                title = Path(path).stem.replace("_", " ").strip() or os.path.basename(path)
                media_id = self.db.add_local_file(
                    path,
                    title=title,
                    width=info["width"],
                    height=info["height"],
                    duration=info["duration"],
                    fmt=info["format"],
                    size_bytes=info["size_bytes"],
                    # "animated" decides static Windows wallpaper vs live playback
                    # for .gif/.webp files (see models.MediaItem.kind).
                    meta={"fps": info["fps"],
                          "animated": bool(info.get("animated", False))},
                )
                imported.append(media_id)
                added += 1
            except Exception as error:  # noqa: BLE001
                log.exception("import failed for %s", raw)
                errors.append(f"{os.path.basename(str(raw))}: {error}")
        self.last_import_summary = {"added": added, "existing": existing,
                                    "failed": len(errors)}
        if imported:
            log.info("library import: %d added, %d already present, %d error(s)",
                     added, existing, len(errors))
            self.changed.emit()
        return imported, errors

    def add_from_search(self, result: SearchResult, favorite: bool = False) -> MediaItem:
        item = result.to_media()
        item.is_favorite = favorite
        media_id = self.db.upsert_media(item)
        item = self.db.get_media(media_id) or item
        self.changed.emit()
        return item

    def mark_downloaded(self, media_id: int, file_path: str, size_bytes: int = 0) -> MediaItem | None:
        info = utils.probe_media(file_path)
        self.db.replace_file_path(media_id, file_path, size_bytes)
        item = self.db.get_media(media_id)
        if item is not None:
            item.width = info["width"] or item.width
            item.height = info["height"] or item.height
            item.duration = info["duration"] or item.duration
            item.format = info["format"] or item.format
            item.thumb_path = None
            self.db.upsert_media(item)
            self.changed.emit()
        return self.db.get_media(media_id)

    # -------------------------------------------------------------------- edit
    def toggle_favorite(self, media_id: int) -> bool:
        value = self.db.toggle_favorite(media_id)
        self.changed.emit()
        return value

    def set_favorite(self, media_id: int, value: bool) -> None:
        self.db.set_favorite(media_id, value)
        self.changed.emit()

    def touch_used(self, media_id: int) -> None:
        self.db.touch_used(media_id)

    def remove_record(self, media_id: int, delete_file: bool = False) -> str | None:
        """Remove a library entry; optionally delete the file after confirmation."""
        item = self.db.get_media(media_id)
        if item is None:
            return None
        if delete_file:
            for path in (item.file_path, item.optimized_path):
                if not path or not os.path.exists(path):
                    continue
                try:
                    os.remove(path)
                except OSError as error:
                    log.warning("could not delete %s: %s", path, error)
                    return str(error)
        self.db.delete_media(media_id)
        self.changed.emit()
        return None

    def file_exists(self, item: MediaItem) -> bool:
        return bool(item.file_path and os.path.exists(item.file_path))

    def library_dir(self) -> Path:
        raw = self.settings.get("storage.library_dir") or str(paths.DEFAULT_LIBRARY_DIR)
        path = paths.expand(raw)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return path
