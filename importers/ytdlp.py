"""yt-dlp based provider implementation shared by YouTube and TikTok."""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

from core.logger import get_logger
from importers.base import (
    ImportCancelled,
    ImportError,
    LinkInfo,
    base_ydl_options,
    choose_best_dimensions,
    friendly_download_error,
)

log = get_logger("importers.ytdlp")


class YtDlpProvider:
    key = ""
    label = ""

    def __init__(self, max_height: int = 1080) -> None:
        self.max_height = max(360, int(max_height or 1080))

    # --------------------------------------------------------------- overrides
    def video_format(self, max_height: int) -> str:
        height = max(360, int(max_height or 1080))
        return (f"bv*[ext=mp4][height<={height}]+ba[ext=m4a]/"
                f"b[ext=mp4][height<={height}]/bv*[height<={height}]+ba/"
                f"b[height<={height}]/b")

    # ------------------------------------------------------------------ fetch
    def fetch_info(self, url: str) -> LinkInfo:
        from yt_dlp import YoutubeDL

        options = base_ydl_options()
        options.update({"skip_download": True, "noplaylist": True})
        try:
            with YoutubeDL(options) as ydl:
                data = ydl.extract_info(url, download=False)
        except Exception as error:  # noqa: BLE001
            log.warning("metadata failed for %s: %s", url, error)
            raise friendly_download_error(error) from error
        data = self._first_entry(data)
        if not data:
            raise ImportError("This link does not contain a video", "empty")
        width, height, fps = choose_best_dimensions(data)
        filesize = int(data.get("filesize") or data.get("filesize_approx") or 0)
        return LinkInfo(
            source=self.key,
            video_id=str(data.get("id") or ""),
            url=url,
            title=str(data.get("title") or data.get("fulltitle") or "").strip(),
            author=str(data.get("uploader") or data.get("channel") or
                       data.get("uploader_id") or "").strip(),
            duration=float(data.get("duration") or 0.0),
            width=width,
            height=height,
            fps=fps,
            ext=str(data.get("ext") or "mp4"),
            thumbnail_url=str(data.get("thumbnail") or ""),
            webpage_url=str(data.get("webpage_url") or url),
            description=str(data.get("description") or ""),
            filesize=filesize,
        )

    @staticmethod
    def _first_entry(data: dict | None) -> dict | None:
        if not data:
            return None
        if data.get("_type") in ("playlist", "multi_video"):
            entries = [entry for entry in (data.get("entries") or []) if entry]
            return entries[0] if entries else None
        return data

    # --------------------------------------------------------------- download
    def download(self, url: str, dest_dir: str | os.PathLike, *,
                 max_height: int, progress: Callable[[dict], None] | None = None,
                 cancel: threading.Event | None = None) -> tuple[str, dict]:
        from yt_dlp import YoutubeDL

        target_dir = Path(dest_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        options = base_ydl_options()
        options.update({
            "format": self.video_format(max_height),
            "merge_output_format": "mp4",
            "outtmpl": str(target_dir / "%(id)s.%(ext)s"),
            "overwrites": True,
        })

        def hook(data: dict) -> None:
            if cancel is not None and cancel.is_set():
                raise ImportCancelled("Import cancelled")
            if progress is not None:
                progress(data)

        options["progress_hooks"] = [hook]
        try:
            with YoutubeDL(options) as ydl:
                data = ydl.extract_info(url, download=True)
        except ImportCancelled:
            raise
        except Exception as error:  # noqa: BLE001
            if cancel is not None and cancel.is_set():
                raise ImportCancelled("Import cancelled") from error
            log.warning("download failed for %s: %s", url, error)
            raise friendly_download_error(error) from error
        data = self._first_entry(data) or {}
        path = self._find_downloaded_file(target_dir)
        if not path:
            raise ImportError("The video file was not created", "download")
        return path, data

    @staticmethod
    def _find_downloaded_file(directory: Path) -> str | None:
        candidates: list[Path] = []
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() in (".part", ".ytdl", ".temp"):
                continue
            if path.suffix.lower() in (".mp4", ".webm", ".mkv", ".mov", ".m4v"):
                candidates.append(path)
        if not candidates:
            return None
        return str(max(candidates, key=lambda item: item.stat().st_size))
