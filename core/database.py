"""SQLite storage for the library, favourites and download queue."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from core.models import DownloadTask, MediaItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'local',
    source_id   TEXT NOT NULL DEFAULT '',
    file_path   TEXT,
    page_url    TEXT,
    thumb_path  TEXT,
    width       INTEGER NOT NULL DEFAULT 0,
    height      INTEGER NOT NULL DEFAULT 0,
    duration    REAL NOT NULL DEFAULT 0,
    format      TEXT NOT NULL DEFAULT '',
    size_bytes  INTEGER NOT NULL DEFAULT 0,
    original_path TEXT NOT NULL DEFAULT '',
    optimized_path TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL DEFAULT '',
    author      TEXT NOT NULL DEFAULT '',
    aspect      TEXT NOT NULL DEFAULT '',
    added_at    TEXT NOT NULL DEFAULT '',
    last_used_at TEXT NOT NULL DEFAULT '',
    is_favorite INTEGER NOT NULL DEFAULT 0,
    favorite_at TEXT NOT NULL DEFAULT '',
    meta        TEXT NOT NULL DEFAULT '{}',
    UNIQUE (source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_media_favorite ON media(is_favorite);
CREATE INDEX IF NOT EXISTS idx_media_file ON media(file_path);

CREATE TABLE IF NOT EXISTS downloads (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id         INTEGER,
    title            TEXT NOT NULL DEFAULT '',
    url              TEXT NOT NULL DEFAULT '',
    dest_path        TEXT NOT NULL DEFAULT '',
    total_bytes      INTEGER NOT NULL DEFAULT 0,
    downloaded_bytes INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'queued',
    error            TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL DEFAULT '',
    updated_at       TEXT NOT NULL DEFAULT '',
    source           TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
"""

SORT_SQL = {
    "recent": "COALESCE(NULLIF(last_used_at,''), added_at) DESC, id DESC",
    "added": "added_at DESC, id DESC",
    "title": "title COLLATE NOCASE ASC",
    "duration": "duration DESC",
    "resolution": "(width * height) DESC",
}


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def path_id(path: str) -> str:
    return hashlib.sha1(os.path.normcase(os.path.abspath(str(path))).encode("utf-8")).hexdigest()


class Database:
    """Thread-safe SQLite wrapper (one connection + a lock)."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._migrate_locked()
            self._conn.commit()

    def _migrate_locked(self) -> None:
        """Add new media columns to databases created by older versions."""
        existing = {row["name"] for row in
                    self._conn.execute("PRAGMA table_info(media)").fetchall()}
        additions = {
            "original_path": "TEXT NOT NULL DEFAULT ''",
            "optimized_path": "TEXT NOT NULL DEFAULT ''",
            "imported_at": "TEXT NOT NULL DEFAULT ''",
            "author": "TEXT NOT NULL DEFAULT ''",
            "aspect": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in additions.items():
            if name not in existing:
                self._conn.execute(f"ALTER TABLE media ADD COLUMN {name} {definition}")

    # ------------------------------------------------------------------ utils
    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
                self._conn.close()
            except sqlite3.Error:
                pass

    def _execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur

    def _query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, tuple(params)).fetchall())

    # ------------------------------------------------------------------ media
    def upsert_media(self, item: MediaItem) -> int:
        """Insert or update a media row, returning its id."""
        now = now_iso()
        if not item.added_at:
            item.added_at = now
        if not item.source_id:
            item.source_id = path_id(item.file_path or item.title)
        meta = json.dumps(item.meta or {}, ensure_ascii=False)
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO media (title, source, source_id, file_path, page_url, thumb_path,
                                   width, height, duration, format, size_bytes,
                                   original_path, optimized_path, imported_at, author, aspect,
                                   added_at, last_used_at, is_favorite, favorite_at, meta)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source, source_id) DO UPDATE SET
                    title=excluded.title,
                    file_path=COALESCE(excluded.file_path, media.file_path),
                    page_url=COALESCE(excluded.page_url, media.page_url),
                    thumb_path=COALESCE(excluded.thumb_path, media.thumb_path),
                    width=excluded.width, height=excluded.height,
                    duration=excluded.duration, format=excluded.format,
                    size_bytes=CASE WHEN excluded.size_bytes > 0 THEN excluded.size_bytes ELSE media.size_bytes END,
                    original_path=CASE WHEN excluded.original_path<>'' THEN excluded.original_path ELSE media.original_path END,
                    optimized_path=CASE WHEN excluded.optimized_path<>'' THEN excluded.optimized_path ELSE media.optimized_path END,
                    imported_at=CASE WHEN excluded.imported_at<>'' THEN excluded.imported_at ELSE media.imported_at END,
                    author=CASE WHEN excluded.author<>'' THEN excluded.author ELSE media.author END,
                    aspect=CASE WHEN excluded.aspect<>'' THEN excluded.aspect ELSE media.aspect END,
                    meta=excluded.meta
                """,
                (
                    item.title, item.source, item.source_id, item.file_path, item.page_url,
                    item.thumb_path, item.width, item.height, item.duration, item.format,
                    item.size_bytes, item.original_path, item.optimized_path,
                    item.imported_at, item.author, item.aspect, item.added_at,
                    item.last_used_at, 1 if item.is_favorite else 0, item.favorite_at, meta,
                ),
            )
            self._conn.commit()
            if item.is_favorite:
                self._conn.execute(
                    "UPDATE media SET is_favorite=1, favorite_at=? WHERE source=? AND source_id=?",
                    (item.favorite_at or now, item.source, item.source_id),
                )
                self._conn.commit()
            row = self._conn.execute(
                "SELECT id FROM media WHERE source=? AND source_id=?",
                (item.source, item.source_id),
            ).fetchone()
            item.id = int(row["id"]) if row else int(cur.lastrowid)
            return item.id

    def add_local_file(self, path: str, title: str = "", width: int = 0, height: int = 0,
                       duration: float = 0.0, fmt: str = "", size_bytes: int = 0,
                       meta: dict | None = None) -> int:
        item = MediaItem(
            title=title or Path(path).stem,
            source="local",
            source_id=path_id(path),
            file_path=str(path),
            width=width,
            height=height,
            duration=duration,
            format=(fmt or Path(path).suffix.lstrip(".")).upper(),
            size_bytes=size_bytes or (os.path.getsize(path) if os.path.exists(path) else 0),
            added_at=now_iso(),
            meta=meta or {},
        )
        return self.upsert_media(item)

    def get_media(self, media_id: int) -> MediaItem | None:
        rows = self._query("SELECT * FROM media WHERE id=?", (media_id,))
        return MediaItem.from_row(rows[0]) if rows else None

    def get_by_source(self, source: str, source_id: str) -> MediaItem | None:
        rows = self._query(
            "SELECT * FROM media WHERE source=? AND source_id=?", (source, str(source_id))
        )
        return MediaItem.from_row(rows[0]) if rows else None

    def find_by_file(self, path: str) -> MediaItem | None:
        rows = self._query("SELECT * FROM media WHERE file_path=?", (str(path),))
        return MediaItem.from_row(rows[0]) if rows else None

    def list_library(self, search: str = "", sort: str = "added",
                     kind: str = "all", favorites_only: bool = False) -> list[MediaItem]:
        where = ["file_path IS NOT NULL", "file_path <> ''"]
        params: list[Any] = []
        if favorites_only:
            where.append("is_favorite=1")
        if search:
            where.append("(title LIKE ? OR meta LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])
        order = SORT_SQL.get(sort, SORT_SQL["added"])
        rows = self._query(f"SELECT * FROM media WHERE {' AND '.join(where)} ORDER BY {order}",
                           params)
        items = [MediaItem.from_row(r) for r in rows]
        if kind and kind != "all":
            items = [m for m in items if m.kind == kind]
        return items

    def list_favorites(self, search: str = "", sort: str = "added") -> list[MediaItem]:
        where = ["is_favorite=1"]
        params: list[Any] = []
        if search:
            where.append("(title LIKE ? OR meta LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])
        order = SORT_SQL.get(sort, SORT_SQL["added"])
        return [MediaItem.from_row(r) for r in
                self._query(f"SELECT * FROM media WHERE {' AND '.join(where)} ORDER BY {order}",
                            params)]

    def list_remote(self, search: str = "") -> list[MediaItem]:
        where = ["(file_path IS NULL OR file_path = '')"]
        params: list[Any] = []
        if search:
            where.append("(title LIKE ? OR meta LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])
        rows = self._query(
            f"SELECT * FROM media WHERE {' AND '.join(where)} ORDER BY added_at DESC", params)
        return [MediaItem.from_row(r) for r in rows]

    def recent(self, limit: int = 6) -> list[MediaItem]:
        rows = self._query(
            "SELECT * FROM media WHERE file_path IS NOT NULL AND file_path <> '' "
            "AND last_used_at <> '' ORDER BY last_used_at DESC LIMIT ?", (limit,))
        return [MediaItem.from_row(r) for r in rows]

    def set_favorite(self, media_id: int, value: bool) -> None:
        self._execute("UPDATE media SET is_favorite=?, favorite_at=? WHERE id=?",
                      (1 if value else 0, now_iso() if value else "", media_id))

    def toggle_favorite(self, media_id: int) -> bool:
        item = self.get_media(media_id)
        if not item:
            return False
        value = not item.is_favorite
        self.set_favorite(media_id, value)
        return value

    def touch_used(self, media_id: int) -> None:
        self._execute("UPDATE media SET last_used_at=? WHERE id=?", (now_iso(), media_id))

    def delete_media(self, media_id: int) -> None:
        self._execute("DELETE FROM media WHERE id=?", (media_id,))

    def replace_file_path(self, media_id: int, path: str, size: int = 0) -> None:
        self._execute(
            "UPDATE media SET file_path=?, size_bytes=CASE WHEN ?>0 THEN ? ELSE size_bytes END "
            "WHERE id=?", (path, size, size, media_id))

    def update_import_info(self, media_id: int, *, original_path: str = "",
                           optimized_path: str = "", imported_at: str = "",
                           author: str = "", aspect: str = "", width: int = 0,
                           height: int = 0, duration: float = 0.0,
                           size_bytes: int = 0) -> None:
        """Update the import-related columns without touching other fields."""
        fields = []
        params: list[Any] = []
        for column, value in (
            ("original_path", original_path),
            ("optimized_path", optimized_path),
            ("imported_at", imported_at),
            ("author", author),
            ("aspect", aspect),
        ):
            if value:
                fields.append(f"{column}=?")
                params.append(value)
        if width > 0:
            fields.append("width=?")
            params.append(int(width))
        if height > 0:
            fields.append("height=?")
            params.append(int(height))
        if duration > 0:
            fields.append("duration=?")
            params.append(float(duration))
        if size_bytes > 0:
            fields.append("size_bytes=?")
            params.append(int(size_bytes))
        if not fields:
            return
        params.append(int(media_id))
        self._execute(f"UPDATE media SET {', '.join(fields)} WHERE id=?", params)

    # ------------------------------------------------------------------ stats
    def stats(self) -> dict[str, int]:
        def scalar(sql: str) -> int:
            rows = self._query(sql)
            return int(rows[0][0]) if rows else 0

        return {
            "library": scalar(
                "SELECT COUNT(*) FROM media WHERE file_path IS NOT NULL AND file_path <> ''"),
            "favorites": scalar("SELECT COUNT(*) FROM media WHERE is_favorite=1"),
            "downloads": scalar("SELECT COUNT(*) FROM media WHERE source <> 'local' "
                                "AND file_path IS NOT NULL AND file_path <> ''"),
            "remote_favorites": scalar(
                "SELECT COUNT(*) FROM media WHERE is_favorite=1 "
                "AND (file_path IS NULL OR file_path='')"),
        }

    # -------------------------------------------------------------- downloads
    def add_download(self, task: DownloadTask) -> int:
        now = now_iso()
        task.created_at = task.created_at or now
        task.updated_at = now
        cur = self._execute(
            """INSERT INTO downloads (media_id, title, url, dest_path, total_bytes,
                                      downloaded_bytes, status, error, created_at, updated_at, source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (task.media_id, task.title, task.url, task.dest_path, task.total_bytes,
             task.downloaded_bytes, task.status, task.error, task.created_at, task.updated_at,
             task.source),
        )
        task.id = int(cur.lastrowid)
        return task.id

    def update_download(self, task: DownloadTask) -> None:
        if task.id is None:
            return
        task.updated_at = now_iso()
        self._execute(
            """UPDATE downloads SET media_id=?, title=?, url=?, dest_path=?, total_bytes=?,
               downloaded_bytes=?, status=?, error=?, updated_at=?, source=? WHERE id=?""",
            (task.media_id, task.title, task.url, task.dest_path, task.total_bytes,
             task.downloaded_bytes, task.status, task.error, task.updated_at, task.source,
             task.id),
        )

    def list_downloads(self, statuses: tuple[str, ...] | None = None) -> list[DownloadTask]:
        if statuses:
            marks = ",".join("?" for _ in statuses)
            rows = self._query(
                f"SELECT * FROM downloads WHERE status IN ({marks}) ORDER BY id DESC",
                statuses)
        else:
            rows = self._query("SELECT * FROM downloads ORDER BY id DESC")
        return [DownloadTask.from_row(r) for r in rows]

    def get_download(self, download_id: int) -> DownloadTask | None:
        rows = self._query("SELECT * FROM downloads WHERE id=?", (download_id,))
        return DownloadTask.from_row(rows[0]) if rows else None

    def delete_download(self, download_id: int) -> None:
        self._execute("DELETE FROM downloads WHERE id=?", (download_id,))
