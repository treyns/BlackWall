"""Download queue: resumable HTTP downloads with pause/cancel/retry."""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from config import paths
from core import utils
from core.database import Database
from core.logger import get_logger
from core.models import DownloadTask, MediaItem, SearchResult

log = get_logger("downloads")

USER_AGENT = "BlackWall/1.0 (live wallpaper app)"


class DownloadManager(QObject):
    changed = Signal()
    item_completed = Signal(int, str)  # media_id, file path
    item_failed = Signal(int, str)

    def __init__(self, db: Database, settings, library, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.settings = settings
        self.library = library
        self._tasks: dict[int, DownloadTask] = {}
        self._threads: dict[int, threading.Thread] = {}
        self._cancel: dict[int, threading.Event] = {}
        self._pause: dict[int, threading.Event] = {}
        self._lock = threading.RLock()
        self._ticker = QTimer(self)
        self._ticker.setInterval(700)
        self._ticker.timeout.connect(self._emit_changed)
        self._ticker.start()
        self._load_pending()

    # ------------------------------------------------------------------ public
    def tasks(self) -> list[DownloadTask]:
        with self._lock:
            return sorted(self._tasks.values(), key=lambda task: task.id or 0, reverse=True)

    def get(self, download_id: int) -> DownloadTask | None:
        return self._tasks.get(download_id)

    def pending_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t.status in ("queued", "downloading", "paused"))

    def download_dir(self) -> Path:
        raw = self.settings.get("storage.download_dir") or str(paths.DEFAULT_DOWNLOAD_DIR)
        path = paths.expand(raw)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return path

    def start_download(self, result: SearchResult) -> DownloadTask:
        """Create a download task for a search result and start it."""
        url = result.download_url or result.video_url
        if not url:
            raise ValueError("This result has no downloadable video URL")
        media = self.library.add_from_search(result)
        if media.id is None:
            raise ValueError("Could not register media")
        ext = os.path.splitext(url.split("?")[0])[1].lower() or ".mp4"
        base = utils.safe_filename(result.title or result.source_id)
        dest = self.download_dir() / f"{base}_{result.provider}{ext}"
        counter = 1
        while dest.exists():
            dest = self.download_dir() / f"{base}_{result.provider}_{counter}{ext}"
            counter += 1

        task = DownloadTask(
            media_id=media.id,
            title=result.title or base,
            url=url,
            dest_path=str(dest),
            status="queued",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            source=result.provider,
        )
        self.db.add_download(task)
        with self._lock:
            self._tasks[task.id] = task
        self.changed.emit()
        self._start_task(task)
        return task

    def pause(self, download_id: int) -> None:
        task = self._tasks.get(download_id)
        if task is None or task.status not in ("downloading", "queued"):
            return
        task.status = "paused"
        if download_id in self._pause:
            self._pause[download_id].set()
        self.db.update_download(task)
        self.changed.emit()

    def resume(self, download_id: int) -> None:
        task = self._tasks.get(download_id)
        if task is None or task.status not in ("paused", "error", "queued"):
            return
        if download_id in self._threads and self._threads[download_id].is_alive():
            self._pause[download_id].clear()
            task.status = "downloading"
            self.changed.emit()
            return
        task.status = "queued"
        task.error = ""
        self._start_task(task)

    def cancel(self, download_id: int) -> None:
        task = self._tasks.get(download_id)
        if task is None:
            return
        if download_id in self._cancel:
            self._cancel[download_id].set()
        if download_id in self._pause:
            self._pause[download_id].clear()
        task.status = "cancelled"
        self.db.update_download(task)
        try:
            if os.path.exists(task.dest_path):
                os.remove(task.dest_path)
        except OSError:
            pass
        self.changed.emit()

    def retry(self, download_id: int) -> None:
        task = self._tasks.get(download_id)
        if task is None:
            return
        self.cancel(download_id) if task.status == "downloading" else None
        task.error = ""
        task.status = "queued"
        self.db.update_download(task)
        self._start_task(task)

    def remove(self, download_id: int) -> None:
        task = self._tasks.get(download_id)
        if task is None:
            return
        self.cancel(download_id)
        with self._lock:
            self._tasks.pop(download_id, None)
        self.db.delete_download(download_id)
        self.changed.emit()

    def shutdown(self) -> None:
        for event in self._cancel.values():
            event.set()
        for event in self._pause.values():
            event.clear()

    # ---------------------------------------------------------------- internal
    def _load_pending(self) -> None:
        for task in self.db.list_downloads(("queued", "downloading", "paused", "error")):
            if task.status == "downloading":
                task.status = "paused"
                self.db.update_download(task)
            self._tasks[task.id] = task

    def _start_task(self, task: DownloadTask) -> None:
        if task.id is None:
            return
        cancel_event = threading.Event()
        pause_event = threading.Event()
        self._cancel[task.id] = cancel_event
        self._pause[task.id] = pause_event
        thread = threading.Thread(target=self._run, args=(task, cancel_event, pause_event),
                                  daemon=True, name=f"download-{task.id}")
        self._threads[task.id] = thread
        thread.start()

    def _run(self, task: DownloadTask, cancel: threading.Event,
             pause: threading.Event) -> None:
        import requests

        dest = Path(task.dest_path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            existing = dest.stat().st_size if dest.exists() else 0
            headers = {"User-Agent": USER_AGENT}
            if existing > 0:
                headers["Range"] = f"bytes={existing}-"
            with requests.get(task.url, headers=headers, stream=True, timeout=30) as response:
                if response.status_code == 416:
                    raise OSError("File already complete")
                response.raise_for_status()
                if existing > 0 and response.status_code != 206:
                    existing = 0
                total = int(response.headers.get("Content-Length") or 0) + existing
                with self._lock:
                    task.total_bytes = total
                    task.downloaded_bytes = existing
                    task.status = "downloading"
                self.db.update_download(task)

                last_emit = time.time()
                last_bytes = existing
                last_time = time.time()
                mode = "ab" if existing else "wb"
                with open(dest, mode) as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if cancel.is_set():
                            return
                        while pause.is_set():
                            time.sleep(0.15)
                            if cancel.is_set():
                                return
                        if not chunk:
                            continue
                        handle.write(chunk)
                        task.downloaded_bytes += len(chunk)
                        now = time.time()
                        if now - last_emit > 0.25:
                            elapsed = max(0.001, now - last_time)
                            task.speed = (task.downloaded_bytes - last_bytes) / elapsed
                            if task.speed > 0 and task.total_bytes > task.downloaded_bytes:
                                task.eta = (task.total_bytes - task.downloaded_bytes) / task.speed
                            last_bytes = task.downloaded_bytes
                            last_time = now
                            last_emit = now
                            self.db.update_download(task)
            if cancel.is_set():
                return
            self._on_complete(task)
        except Exception as error:  # noqa: BLE001
            log.warning("download failed: %s", error)
            with self._lock:
                task.status = "error"
                task.error = str(error)[:300]
            self.db.update_download(task)
            if task.media_id:
                self.item_failed.emit(task.media_id, task.error)
            self.changed.emit()

    def _on_complete(self, task: DownloadTask) -> None:
        if not task.dest_path or not os.path.exists(task.dest_path):
            with self._lock:
                task.status = "error"
                task.error = "Downloaded file is missing"
            self.db.update_download(task)
            self.changed.emit()
            return
        file_size = os.path.getsize(task.dest_path)
        # Register the file in the library BEFORE the task is reported as complete,
        # so the UI never sees a completed download without a usable library row.
        if task.media_id:
            try:
                self.library.mark_downloaded(task.media_id, task.dest_path, file_size)
            except Exception:  # noqa: BLE001
                log.exception("could not register downloaded file in the library")
        with self._lock:
            task.downloaded_bytes = file_size
            task.total_bytes = max(task.total_bytes, task.downloaded_bytes)
            task.status = "completed"
            task.speed = 0.0
            task.eta = 0.0
        self.db.update_download(task)
        log.info("download complete: %s", task.dest_path)
        if task.media_id:
            self.item_completed.emit(task.media_id, task.dest_path)
        self.changed.emit()

    def _emit_changed(self) -> None:
        # Keep the UI in sync cheaply; only emit when something is running.
        if any(t.status == "downloading" for t in self._tasks.values()):
            self.changed.emit()
