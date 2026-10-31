"""Thumbnail service: async generation (video frames) and HTTP caching."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QRectF, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from config import paths
from core import utils
from ui import icons
from ui.theme import current_theme

_TABLE = 900  # max images kept in RAM


class _WorkerSignals(QObject):
    done = Signal(str, QImage)


class _ThumbWorker(QRunnable):
    def __init__(self, key: str, source: str, cache_dir: Path, remote_dir: Path,
                 width: int, service: QObject | None = None) -> None:
        super().__init__()
        self.key = key
        self.source = source
        self.cache_dir = cache_dir
        self.remote_dir = remote_dir
        self.width = width
        self.signals = _WorkerSignals(service)

    def run(self) -> None:  # noqa: D401 - QRunnable API
        image = QImage()
        try:
            if self.source.startswith(("http://", "https://")):
                image = self._load_remote()
            else:
                image = self._load_local()
        except Exception:  # noqa: BLE001 - thumbnails must never crash the UI
            image = QImage()
        try:
            self.signals.done.emit(self.key, image)
        except RuntimeError:
            # The service was destroyed while the worker was still running.
            pass

    # ------------------------------------------------------------------ local
    def _load_local(self) -> QImage:
        path = self.source
        if not path or not os.path.exists(path):
            return QImage()
        digest = hashlib.sha1(os.path.normcase(path).encode("utf-8")).hexdigest()
        cache_file = self.cache_dir / f"{digest}.jpg"
        if not cache_file.exists():
            utils.thumbnail_for(path, cache_file, width=self.width)
        if cache_file.exists():
            return QImage(str(cache_file))
        return QImage()

    # ----------------------------------------------------------------- remote
    def _load_remote(self) -> QImage:
        url = self.source
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        cache_file = self.remote_dir / f"{digest}.jpg"
        if not cache_file.exists():
            import requests

            headers = {"User-Agent": "BlackWall/1.0 (+live wallpaper app)"}
            response = requests.get(url, timeout=20, headers=headers, stream=True)
            response.raise_for_status()
            data = response.content
            if not data:
                return QImage()
            cache_file.write_bytes(data)
        image = QImage(str(cache_file))
        if image.isNull():
            return QImage()
        if image.width() > self.width:
            image = image.scaledToWidth(self.width, Qt.TransformationMode.SmoothTransformation)
        return image


class ThumbService(QObject):
    ready = Signal(str, QImage)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache: dict[str, QImage] = {}
        self._pending: set[str] = set()
        self._workers: dict[str, _ThumbWorker] = {}
        self._pool = QThreadPool.globalInstance()
        self._cache_dir = paths.THUMBNAILS_DIR
        self._remote_dir = paths.REMOTE_THUMBNAILS_DIR
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._remote_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def get(self, key: str) -> QImage | None:
        return self._cache.get(key)

    def request(self, key: str, source: str, width: int = 520) -> None:
        if not source or key in self._cache or key in self._pending:
            return
        self._pending.add(key)
        worker = _ThumbWorker(key, source, self._cache_dir, self._remote_dir, width, self)
        worker.signals.done.connect(self._on_done, Qt.ConnectionType.QueuedConnection)
        self._workers[key] = worker
        self._pool.start(worker)

    def _on_done(self, key: str, image: QImage) -> None:
        self._pending.discard(key)
        self._workers.pop(key, None)
        if not image.isNull():
            if len(self._cache) >= _TABLE:
                self._cache.pop(next(iter(self._cache)), None)
            self._cache[key] = image
            self.ready.emit(key, image)

    def clear_cache(self) -> None:
        """Drop memory cache and delete cached thumbnail files."""
        self._cache.clear()
        for folder in (self._cache_dir, self._remote_dir):
            try:
                for file in folder.glob("*.jpg"):
                    file.unlink()
            except OSError:
                pass


_SERVICE: ThumbService | None = None


def get_service() -> ThumbService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = ThumbService()
    return _SERVICE


class ThumbnailWidget(QWidget):
    """Rounded thumbnail that loads a local file or a remote image asynchronously."""

    def __init__(self, width: int = 300, height: int = 170,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self.setFixedSize(theme.px(width), theme.px(height))
        self._image: QImage | None = None
        self._key: str = ""
        self._source: str = ""
        self._radius: int = theme.px(10)
        self._service = get_service()
        self._service.ready.connect(self._on_ready)

    def set_source(self, source: str, key: str | None = None) -> None:
        self._source = source or ""
        self._key = key or self._source
        if not self._source:
            self._image = None
            self.update()
            return
        cached = self._service.get(self._key)
        if cached is not None:
            self._image = cached
            self.update()
            return
        self._image = None
        self.update()
        self._service.request(self._key, self._source)

    def _on_ready(self, key: str, image: QImage) -> None:
        if key == self._key:
            self._image = image
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        theme = current_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        painter.setClipPath(path)
        painter.fillRect(rect, QColor(theme.color("surface")))

        image = self._image
        if image is not None and not image.isNull():
            iw, ih = image.width(), image.height()
            if iw > 0 and ih > 0:
                scale = max(self.width() / iw, self.height() / ih)
                draw_w, draw_h = iw * scale, ih * scale
                painter.drawImage(
                    QRectF((self.width() - draw_w) / 2, (self.height() - draw_h) / 2,
                           draw_w, draw_h),
                    image,
                )
        else:
            painter.setPen(QPen(QColor(theme.color("border"))))
            icon_pix = icons.pixmap("image", theme.color("border"), theme.px(34))
            painter.drawPixmap(
                int((self.width() - theme.px(34)) / 2),
                int((self.height() - theme.px(34)) / 2),
                icon_pix,
            )
        painter.end()
