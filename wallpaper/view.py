"""Video / GIF / image renderer used inside a desktop window.

The view paints frames itself (no OpenGL, no extra processes) and enforces the
FPS cap BEFORE converting frames, which is where most CPU is spent.
"""
from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QImage, QImageReader, QMovie, QPainter
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import QWidget

from core.logger import get_logger

log = get_logger("player")


class MediaView(QWidget):
    error = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._kind = ""
        self._path = ""
        self._image: QImage | None = None
        self._static_full: QImage | None = None
        self._player: QMediaPlayer | None = None
        self._sink: QVideoSink | None = None
        self._audio: QAudioOutput | None = None
        self._movie: QMovie | None = None
        self._fit = "cover"
        self._fps_cap = 30
        self._render_scale = 1.0
        self._speed = 1.0
        self._muted = True
        self._volume = 0
        self._loop = True
        self._paused = False
        self._paint_times: deque[float] = deque(maxlen=240)
        self._last_frame_time = 0.0
        self._last_frame = 0.0

    # ------------------------------------------------------------------ source
    def set_source(self, path: str, kind: str, fit: str = "cover", muted: bool = True,
                   volume: int = 0, speed: float = 1.0, fps_cap: int = 30,
                   loop: bool = True) -> None:
        self._stop_current()
        self._path = path
        self._kind = kind
        self._fit = fit
        self._muted = muted
        self._volume = volume
        self._speed = speed
        self._fps_cap = max(1, fps_cap)
        self._loop = loop
        self._image = None
        self._paused = False
        self._last_frame_time = 0.0
        self._paint_times.clear()

        if kind == "video":
            self._setup_video(path)
        elif kind == "animation":
            self._setup_animation(path)
        else:
            self._setup_image(path)
        self.update()

    def _stop_current(self) -> None:
        if self._player is not None:
            try:
                self._player.stop()
                self._player.setSource(QUrl())
                self._player.deleteLater()
            except Exception:  # noqa: BLE001
                pass
            self._player = None
        self._sink = None
        self._audio = None
        if self._movie is not None:
            try:
                self._movie.stop()
                self._movie.deleteLater()
            except Exception:  # noqa: BLE001
                pass
            self._movie = None
        self._image = None
        self._static_full = None

    # ------------------------------------------------------------------- video
    def _setup_video(self, path: str) -> None:
        self._player = QMediaPlayer(self)
        self._sink = QVideoSink(self)
        self._player.setVideoSink(self._sink)
        self._sink.videoFrameChanged.connect(self._on_video_frame)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._apply_audio()
        try:
            self._player.setLoops(-1 if self._loop else 1)
            self._player.setPlaybackRate(self._speed)
        except Exception:  # noqa: BLE001
            pass
        self._player.errorOccurred.connect(self._on_error)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    def _apply_audio(self) -> None:
        if self._audio is None:
            return
        try:
            self._audio.setMuted(self._muted)
            self._audio.setVolume(max(0.0, min(1.0, self._volume / 100.0)))
        except Exception:  # noqa: BLE001
            pass

    def _on_error(self, error, message: str) -> None:  # noqa: ANN001
        text = message or str(error)
        log.warning("media error: %s (%s)", text, self._path)
        self.error.emit(text)

    def _allow_frame(self) -> bool:
        now = time.monotonic()
        interval = 1.0 / max(1, self._fps_cap)
        if now - self._last_frame_time < interval * 0.92:
            return False
        self._last_frame_time = now
        return True

    def _on_video_frame(self, frame) -> None:  # noqa: ANN001
        if self._paused or not frame.isValid():
            return
        if not self._allow_frame():
            return
        image = frame.toImage()
        if image.isNull():
            return
        self._image = self._scale_image(image)
        self.update()

    # --------------------------------------------------------------- animation
    def _setup_animation(self, path: str) -> None:
        reader = QImageReader(path)
        frames = reader.imageCount()
        if frames <= 1:
            self._setup_image(path)
            return
        self._movie = QMovie(path)
        try:
            self._movie.setCacheMode(QMovie.CacheMode.CacheNone)
        except Exception:  # noqa: BLE001
            pass
        self._movie.setSpeed(max(10, int(100 * self._speed)))
        self._movie.frameChanged.connect(self._on_movie_frame)
        self._movie.start()

    def _on_movie_frame(self, _frame_number: int) -> None:
        if self._paused or self._movie is None:
            return
        if not self._allow_frame():
            return
        pixmap = self._movie.currentPixmap()
        if not pixmap.isNull():
            self._image = self._scale_image(pixmap.toImage())
            self.update()

    # ------------------------------------------------------------------- image
    def _setup_image(self, path: str) -> None:
        image = QImage(path)
        if image.isNull():
            log.warning("cannot load image: %s", path)
            self.error.emit(f"Cannot load image: {path}")
            return
        self._static_full = image
        self._image = self._scale_image(image)
        self.update()

    def _scale_image(self, image: QImage) -> QImage:
        scale = self._render_scale
        if scale >= 0.999 or image.isNull():
            return image
        width = max(2, int(image.width() * scale))
        height = max(2, int(image.height() * scale))
        if width == image.width() and height == image.height():
            return image
        return image.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.FastTransformation)

    # ----------------------------------------------------------------- controls
    def set_fit(self, fit: str) -> None:
        if fit in ("cover", "blur", "contain", "stretch"):
            self._fit = fit
            self.update()

    def set_fps_cap(self, fps: int) -> None:
        self._fps_cap = max(1, int(fps))

    def set_render_scale(self, scale: float) -> None:
        self._render_scale = max(0.5, min(1.0, float(scale)))
        if self._kind == "image" and self._static_full is not None:
            self._image = self._scale_image(self._static_full)
            self.update()

    def set_paused(self, paused: bool) -> None:
        if paused == self._paused:
            return
        self._paused = paused
        if self._player is not None:
            try:
                if paused:
                    self._player.pause()
                else:
                    self._player.play()
            except Exception:  # noqa: BLE001
                pass
        if self._movie is not None:
            try:
                self._movie.setPaused(paused)
            except Exception:  # noqa: BLE001
                pass
        if not paused:
            self._last_frame_time = 0.0

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        self._apply_audio()

    def set_volume(self, volume: int) -> None:
        self._volume = int(volume)
        self._apply_audio()

    def set_loop(self, loop: bool) -> None:
        self._loop = bool(loop)
        if self._player is not None:
            try:
                self._player.setLoops(-1 if self._loop else 1)
            except Exception:  # noqa: BLE001
                pass

    def set_speed(self, speed: float) -> None:
        self._speed = max(0.25, min(4.0, float(speed)))
        if self._player is not None:
            try:
                self._player.setPlaybackRate(self._speed)
            except Exception:  # noqa: BLE001
                pass
        if self._movie is not None:
            try:
                self._movie.setSpeed(max(10, int(100 * self._speed)))
            except Exception:  # noqa: BLE001
                pass

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def media_kind(self) -> str:
        return self._kind

    def measured_fps(self) -> float:
        now = time.monotonic()
        recent = [stamp for stamp in self._paint_times if now - stamp <= 1.5]
        if len(recent) < 2:
            return 0.0
        span = max(0.2, now - recent[0])
        return min(999.0, len(recent) / span)

    def shutdown(self) -> None:
        self._stop_current()
        self.update()

    # -------------------------------------------------------------------- paint
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        image = self._image
        if image is not None and not image.isNull():
            self._paint_times.append(time.monotonic())
            iw, ih = image.width(), image.height()
            width, height = self.width(), self.height()
            if iw > 0 and ih > 0 and width > 0 and height > 0:
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                if self._fit == "blur":
                    # Blurred, enlarged copy fills the screen; the original is
                    # drawn on top without any black bars or cropping.
                    cover = max(width / iw, height / ih)
                    draw_w, draw_h = iw * cover, ih * cover
                    background = image.scaled(max(16, width // 26), max(16, height // 26),
                                              Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                              Qt.TransformationMode.FastTransformation)
                    painter.drawImage(
                        QRectF((width - draw_w) / 2, (height - draw_h) / 2,
                               draw_w, draw_h), background)
                    painter.fillRect(self.rect(), QColor(0, 0, 0, 96))
                    scale = min(width / iw, height / ih)
                    fg_w, fg_h = iw * scale, ih * scale
                    painter.drawImage(QRectF((width - fg_w) / 2, (height - fg_h) / 2,
                                             fg_w, fg_h), image)
                elif self._fit == "stretch":
                    painter.drawImage(QRectF(0, 0, width, height), image)
                else:
                    scale = (max(width / iw, height / ih) if self._fit == "cover"
                             else min(width / iw, height / ih))
                    draw_w, draw_h = iw * scale, ih * scale
                    target = QRectF((width - draw_w) / 2, (height - draw_h) / 2,
                                    draw_w, draw_h)
                    painter.drawImage(target, image)
        painter.end()
