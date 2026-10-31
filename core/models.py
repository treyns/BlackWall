"""Data models shared by the UI, database and playback engine."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


def _parse_json(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def media_kind(path_or_format: str | None) -> str:
    """Return ``video`` / ``animation`` / ``image`` for a path or extension."""
    from config.constants import ANIMATED_EXTS, IMAGE_EXTS, VIDEO_EXTS

    ext = os.path.splitext(str(path_or_format or ""))[1].lower()
    if not ext and path_or_format and str(path_or_format).startswith("."):
        ext = str(path_or_format).lower()
    if ext in ANIMATED_EXTS:
        return "animation"
    if ext in VIDEO_EXTS:
        return "video"
    return "image"


@dataclass
class MediaItem:
    """A library / favourite entry (local file or remote wallpaper)."""

    id: int | None = None
    title: str = ""
    source: str = "local"
    source_id: str = ""
    file_path: str | None = None
    page_url: str | None = None
    thumb_path: str | None = None
    width: int = 0
    height: int = 0
    duration: float = 0.0
    format: str = ""
    size_bytes: int = 0
    original_path: str = ""
    optimized_path: str = ""
    imported_at: str = ""
    author: str = ""
    aspect: str = ""
    added_at: str = ""
    last_used_at: str = ""
    is_favorite: bool = False
    favorite_at: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def is_local(self) -> bool:
        return bool(self.file_path and os.path.exists(self.file_path))

    @property
    def kind(self) -> str:
        ext = os.path.splitext(str(self.file_path or self.format or ""))[1].lower()
        animated = self.meta.get("animated") if isinstance(self.meta, dict) else None
        if ext in (".gif", ".webp") and animated is False:
            return "image"
        return media_kind(self.file_path or self.format)

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width} × {self.height}"
        return "—"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "source_id": self.source_id,
            "file_path": self.file_path,
            "page_url": self.page_url,
            "thumb_path": self.thumb_path,
            "width": self.width,
            "height": self.height,
            "duration": self.duration,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "original_path": self.original_path,
            "optimized_path": self.optimized_path,
            "imported_at": self.imported_at,
            "author": self.author,
            "aspect": self.aspect,
            "added_at": self.added_at,
            "last_used_at": self.last_used_at,
            "is_favorite": self.is_favorite,
            "favorite_at": self.favorite_at,
            "meta": self.meta,
        }

    @classmethod
    def from_row(cls, row: Any) -> "MediaItem":
        data = dict(row)
        return cls(
            id=data.get("id"),
            title=data.get("title") or "",
            source=data.get("source") or "local",
            source_id=str(data.get("source_id") or ""),
            file_path=data.get("file_path"),
            page_url=data.get("page_url"),
            thumb_path=data.get("thumb_path"),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            duration=float(data.get("duration") or 0),
            format=data.get("format") or "",
            size_bytes=int(data.get("size_bytes") or 0),
            original_path=data.get("original_path") or "",
            optimized_path=data.get("optimized_path") or "",
            imported_at=data.get("imported_at") or "",
            author=data.get("author") or "",
            aspect=data.get("aspect") or "",
            added_at=data.get("added_at") or "",
            last_used_at=data.get("last_used_at") or "",
            is_favorite=bool(data.get("is_favorite")),
            favorite_at=data.get("favorite_at") or "",
            meta=_parse_json(data.get("meta")),
        )


@dataclass
class SearchResult:
    """A video found by a provider (not downloaded)."""

    provider: str
    source_id: str
    title: str = ""
    description: str = ""
    thumbnail_url: str = ""
    preview_url: str = ""
    video_url: str = ""
    download_url: str = ""
    page_url: str = ""
    author: str = ""
    width: int = 0
    height: int = 0
    duration: float = 0.0
    format: str = "mp4"
    tags: list[str] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return f"{self.provider}:{self.source_id}"

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width} × {self.height}"
        return "—"

    @property
    def duration_text(self) -> str:
        if not self.duration:
            return "—"
        seconds = int(round(self.duration))
        return f"{seconds // 60}:{seconds % 60:02d}"

    def to_media(self) -> MediaItem:
        return MediaItem(
            title=self.title,
            source=self.provider,
            source_id=self.source_id,
            page_url=self.page_url,
            thumb_path=self.thumbnail_url,
            width=self.width,
            height=self.height,
            duration=float(self.duration),
            format=self.format,
            meta={
                "download_url": self.download_url or self.video_url,
                "preview_url": self.preview_url or self.video_url,
                "author": self.author,
                "tags": self.tags,
                "files": self.files,
                "description": self.description,
            },
        )

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "source_id": self.source_id,
            "title": self.title,
            "description": self.description,
            "thumbnail_url": self.thumbnail_url,
            "preview_url": self.preview_url,
            "video_url": self.video_url,
            "download_url": self.download_url,
            "page_url": self.page_url,
            "author": self.author,
            "width": self.width,
            "height": self.height,
            "duration": self.duration,
            "format": self.format,
            "tags": list(self.tags),
            "files": list(self.files),
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SearchResult":
        return cls(
            provider=data.get("provider", ""),
            source_id=str(data.get("source_id", "")),
            title=data.get("title", ""),
            description=data.get("description", ""),
            thumbnail_url=data.get("thumbnail_url", ""),
            preview_url=data.get("preview_url", ""),
            video_url=data.get("video_url", ""),
            download_url=data.get("download_url", ""),
            page_url=data.get("page_url", ""),
            author=data.get("author", ""),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
            duration=float(data.get("duration") or 0),
            format=data.get("format", "mp4"),
            tags=list(data.get("tags") or []),
            files=list(data.get("files") or []),
            meta=dict(data.get("meta") or {}),
        )


@dataclass
class MonitorInfo:
    key: str
    name: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    primary: bool = False
    refresh: float = 60.0
    dpr: float = 1.0

    @property
    def resolution(self) -> str:
        return f"{self.width} × {self.height}"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "primary": self.primary,
            "refresh": self.refresh,
            "dpr": self.dpr,
        }


@dataclass
class Assignment:
    """Wallpaper assigned to a monitor."""

    monitor_key: str
    media_id: int | None = None
    file_path: str = ""
    kind: str = "video"
    fit: str = "cover"
    fit_explicit: bool = False
    quality: str = "original"
    fps_cap: int = 0
    paused: bool = False
    muted: bool = True
    volume: int = 0
    speed: float = 1.0
    enabled: bool = True
    source: str = "local"
    title: str = ""

    def to_dict(self) -> dict:
        return {
            "media_id": self.media_id,
            "file_path": self.file_path,
            "kind": self.kind,
            "fit": self.fit,
            "fit_explicit": self.fit_explicit,
            "quality": self.quality,
            "fps_cap": self.fps_cap,
            "paused": self.paused,
            "muted": self.muted,
            "volume": self.volume,
            "speed": self.speed,
            "enabled": self.enabled,
            "source": self.source,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, monitor_key: str, data: dict) -> "Assignment":
        return cls(
            monitor_key=monitor_key,
            media_id=data.get("media_id"),
            file_path=data.get("file_path", ""),
            kind=data.get("kind", "video"),
            fit=data.get("fit", "cover"),
            fit_explicit=bool(data.get("fit_explicit", False)),
            quality=data.get("quality", "original") or "original",
            fps_cap=int(data.get("fps_cap", 0) or 0),
            paused=bool(data.get("paused", False)),
            muted=bool(data.get("muted", True)),
            volume=int(data.get("volume", 0)),
            speed=float(data.get("speed", 1.0)),
            enabled=bool(data.get("enabled", True)),
            source=data.get("source", "local"),
            title=data.get("title", ""),
        )


@dataclass
class DownloadTask:
    id: int | None = None
    media_id: int | None = None
    title: str = ""
    url: str = ""
    dest_path: str = ""
    total_bytes: int = 0
    downloaded_bytes: int = 0
    status: str = "queued"  # queued/downloading/paused/completed/error/cancelled
    error: str = ""
    created_at: str = ""
    updated_at: str = ""
    speed: float = 0.0
    eta: float = 0.0
    source: str = ""

    @property
    def progress(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(1.0, self.downloaded_bytes / self.total_bytes)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "media_id": self.media_id,
            "title": self.title,
            "url": self.url,
            "dest_path": self.dest_path,
            "total_bytes": self.total_bytes,
            "downloaded_bytes": self.downloaded_bytes,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "speed": self.speed,
            "eta": self.eta,
            "source": self.source,
        }

    @classmethod
    def from_row(cls, row: Any) -> "DownloadTask":
        data = dict(row)
        return cls(
            id=data.get("id"),
            media_id=data.get("media_id"),
            title=data.get("title") or "",
            url=data.get("url") or "",
            dest_path=data.get("dest_path") or "",
            total_bytes=int(data.get("total_bytes") or 0),
            downloaded_bytes=int(data.get("downloaded_bytes") or 0),
            status=data.get("status") or "queued",
            error=data.get("error") or "",
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
            source=data.get("source") or "",
        )


@dataclass
class PerfSample:
    cpu: float = 0.0           # BlackWall CPU load, % of total CPU (Task Manager style)
    ram_mb: float = 0.0        # BlackWall working set, MB
    gpu: float | None = None   # BlackWall GPU load, % (None = counter unavailable)
    fps: float = 0.0           # measured rendered wallpaper FPS
    timestamp: float = 0.0
    system_cpu: float = 0.0    # whole-system CPU, %
    system_ram: float = 0.0    # whole-system RAM usage, %
