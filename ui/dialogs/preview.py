"""Video preview dialog with real playback (QtMultimedia).

Used by the Discover page (remote search results) and the Library/Favorites
pages (local library items).  Playback is muted by default, starts only because
the user explicitly opened the dialog, and is fully stopped when the dialog
closes.  Playback problems are reported and the user can always fall back to
""Open source" or "Download".
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core import utils
from core.i18n import tr
from core.logger import get_logger
from core.models import MediaItem, SearchResult, media_kind
from ui import icons
from ui.components.widgets import Badge, Divider, caption, h2, text_label
from ui.theme import current_theme

log = get_logger("preview")

_PANEL_WIDTH = 334
_STAGE_WIDTH = 790
_STAGE_HEIGHT = 444


def _format_time(ms: int | float) -> str:
    seconds = max(0, int((ms or 0) // 1000))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _media_result(item: MediaItem) -> SearchResult:
    """Rebuild a SearchResult from a stored MediaItem (for download/favourite)."""
    meta = item.meta or {}
    return SearchResult(
        provider=item.source,
        source_id=item.source_id,
        title=item.title,
        description=str(meta.get("description") or ""),
        thumbnail_url=item.thumb_path or "",
        preview_url=str(meta.get("preview_url") or ""),
        video_url=str(meta.get("download_url") or ""),
        download_url=str(meta.get("download_url") or ""),
        page_url=item.page_url or "",
        author=str(meta.get("author") or ""),
        width=item.width,
        height=item.height,
        duration=float(item.duration or 0),
        format=item.format or "",
        tags=list(meta.get("tags") or []),
        files=list(meta.get("files") or []),
    )


class PreviewDialog(QDialog):
    """Plays a remote SearchResult or a local MediaItem with real metadata."""

    def __init__(self, ctx, result: SearchResult | MediaItem,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.result = result
        self._is_media = isinstance(result, MediaItem)
        self._media_id = result.id if self._is_media else None
        self._stopped = False
        self._seeking = False
        self._download_started = False
        theme = current_theme()

        self.setObjectName("PreviewDialog")
        self.setWindowTitle(str(getattr(result, "title", "") or tr("Preview")))
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMinimumSize(theme.px(1000), theme.px(600))
        self.resize(theme.px(1100), theme.px(640))

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setMuted(True)          # never autoplay with sound
        self._player.setAudioOutput(self._audio)
        self._favorite = self._read_favorite()

        self._build(theme)
        self._connect()
        self._start_playback()

    # ------------------------------------------------------------------- build
    def _build(self, theme) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(theme.px(18), theme.px(18), theme.px(18), theme.px(18))
        root.setSpacing(theme.px(18))

        # ------------------------------------------------------------ left/stage
        left = QVBoxLayout()
        left.setSpacing(theme.px(10))
        self._stage = QWidget()
        stage_layout = QVBoxLayout(self._stage)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        stage_layout.setSpacing(0)

        self._video = QVideoWidget(self._stage)
        self._video.setMinimumSize(theme.px(560), theme.px(315))
        self._video.setStyleSheet(
            f"background-color: {theme.color('shadow')}; border-radius: {theme.px(10)}px;")
        self._player.setVideoOutput(self._video)
        stage_layout.addWidget(self._video)

        self._image_label = QLabel(self._stage)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setMinimumSize(theme.px(560), theme.px(315))
        self._image_label.setStyleSheet(
            f"background-color: {theme.color('shadow')}; border-radius: {theme.px(10)}px;")
        self._image_label.setVisible(False)
        stage_layout.addWidget(self._image_label)
        left.addWidget(self._stage, 1)

        controls = QHBoxLayout()
        controls.setSpacing(theme.px(10))
        self._play_button = QPushButton()
        self._play_button.setObjectName("IconButton")
        self._play_button.setFixedSize(theme.px(34), theme.px(30))
        self._play_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_button.setToolTip(tr("Pause"))
        self._play_button.clicked.connect(self._toggle_play)
        controls.addWidget(self._play_button)

        self._position = QSlider(Qt.Orientation.Horizontal)
        self._position.setRange(0, 0)
        self._position.setCursor(Qt.CursorShape.PointingHandCursor)
        self._position.setToolTip(tr("Seek"))
        self._position.sliderPressed.connect(self._on_seek_start)
        self._position.sliderReleased.connect(self._on_seek_end)
        self._position.sliderMoved.connect(self._on_seek_move)
        controls.addWidget(self._position, 1)

        self._time_label = text_label("0:00 / 0:00", "Caption")
        self._time_label.setMinimumWidth(theme.px(84))
        controls.addWidget(self._time_label)

        self._mute_button = QPushButton()
        self._mute_button.setObjectName("IconButton")
        self._mute_button.setFixedSize(theme.px(34), theme.px(30))
        self._mute_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_button.setToolTip(tr("Unmute"))
        self._mute_button.clicked.connect(self._toggle_mute)
        controls.addWidget(self._mute_button)
        left.addLayout(controls)
        root.addLayout(left, 1)

        # ------------------------------------------------------------ info panel
        panel = QWidget()
        panel.setFixedWidth(theme.px(_PANEL_WIDTH))
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, theme.px(2), 0, 0)
        panel_layout.setSpacing(theme.px(10))

        badge_row = QHBoxLayout()
        badge_row.setSpacing(theme.px(6))
        self._source_badge = Badge(self._source_text(), accent=True)
        self._resolution_badge = Badge(self._resolution_text(), accent=False)
        badge_row.addWidget(self._source_badge)
        badge_row.addWidget(self._resolution_badge)
        badge_row.addStretch(1)
        panel_layout.addLayout(badge_row)

        title = getattr(self.result, "title", "") or tr("Untitled")
        self._title_label = h2(title)
        self._title_label.setWordWrap(True)
        panel_layout.addWidget(self._title_label)

        meta_parts = [part for part in (
            getattr(self.result, "author", "") or "",
            (self._format_text() or "").upper(),
            utils.human_duration(self._duration()) if self._duration() else "",
            utils.human_size(getattr(self.result, "size_bytes", 0)) if self._is_media else "",
        ) if part and part != "—"]
        self._meta_label = text_label(" · ".join(meta_parts) or "—", "CardMeta")
        self._meta_label.setWordWrap(True)
        panel_layout.addWidget(self._meta_label)

        description = self._description_text()
        if description:
            description_label = caption(description[:320])
            panel_layout.addWidget(description_label)

        panel_layout.addWidget(Divider())

        self._status_label = caption("")
        self._status_label.setVisible(False)
        self._status_label.setWordWrap(True)
        panel_layout.addWidget(self._status_label)

        panel_layout.addStretch(1)

        self._add_button = QPushButton(tr("Add to library"))
        self._add_button.setObjectName("Primary")
        self._add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_button.setIcon(icons.icon("plus", theme.color("accent_text"),
                                           theme.px(16)))
        self._add_button.clicked.connect(self._on_add_to_library)
        panel_layout.addWidget(self._add_button)

        self._download_button = QPushButton(tr("Download"))
        self._download_button.setObjectName("Outline")
        self._download_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_button.setIcon(icons.icon("downloads", theme.color("text"),
                                                theme.px(16)))
        self._download_button.clicked.connect(self._on_download)
        panel_layout.addWidget(self._download_button)

        self._favorite_button = QPushButton(tr("Favorite"))
        self._favorite_button.setObjectName("Outline")
        self._favorite_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._favorite_button.clicked.connect(self._toggle_favorite)
        panel_layout.addWidget(self._favorite_button)

        self._open_button = QPushButton(tr("Open source"))
        self._open_button.setObjectName("LinkButton")
        self._open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_button.setIcon(icons.icon("external", theme.color("accent"),
                                            theme.px(15)))
        self._open_button.clicked.connect(self._open_source)
        panel_layout.addWidget(self._open_button)

        close_button = QPushButton(tr("Close"))
        close_button.setObjectName("Ghost")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.reject)
        panel_layout.addWidget(close_button)

        root.addWidget(panel)

        # buttons whose meaning depends on the item type
        if self._is_media and self.result.is_local:
            self._add_button.setVisible(False)
            self._download_button.setVisible(False)
        if not (getattr(self.result, "page_url", "") or ""):
            self._open_button.setVisible(False)
        self._refresh_favorite_button()
        self._refresh_play_icon()
        self._refresh_mute_icon()

    # ----------------------------------------------------------------- helpers
    def _duration(self) -> float:
        try:
            return float(getattr(self.result, "duration", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    def _source_text(self) -> str:
        if self._is_media:
            source = str(self.result.source or "local")
            return {"local": tr("Local file")}.get(source, source.upper())
        return str(self.result.provider or "").upper()

    def _resolution_text(self) -> str:
        width = int(getattr(self.result, "width", 0) or 0)
        height = int(getattr(self.result, "height", 0) or 0)
        if width and height:
            return f"{width} × {height}"
        return tr("Unknown resolution")

    def _format_text(self) -> str:
        fmt = str(getattr(self.result, "format", "") or "")
        if not fmt and self._is_media and self.result.file_path:
            fmt = os.path.splitext(self.result.file_path)[1].lstrip(".")
        return fmt

    def _description_text(self) -> str:
        if self._is_media:
            return str((self.result.meta or {}).get("description") or "")
        return str(getattr(self.result, "description", "") or "")

    def _play_source(self) -> str:
        if self._is_media:
            path = self.result.file_path or ""
            if path and os.path.exists(path):
                return path
            return str((self.result.meta or {}).get("preview_url") or "")
        return str(self.result.preview_url or self.result.video_url or "")

    def _download_result(self) -> SearchResult:
        if self._is_media:
            return _media_result(self.result)
        return self.result

    # ------------------------------------------------------------------ player
    def _connect(self) -> None:
        self._player.errorOccurred.connect(self._on_player_error)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.playbackStateChanged.connect(self._on_playback_state)
        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)

    def _start_playback(self) -> None:
        source = self._play_source()
        if not source:
            self._show_error(tr("No preview video is available for this item. "
                                "You can still download it or open its source page."))
            self._play_button.setEnabled(False)
            self._position.setEnabled(False)
            return
        kind = media_kind(str(source).split("?")[0])
        if kind == "image":
            pixmap = QPixmap(source)
            if pixmap.isNull():
                self._show_error(tr("Could not load the preview image."))
                return
            scaled = pixmap.scaled(
                current_theme().px(_STAGE_WIDTH), current_theme().px(_STAGE_HEIGHT),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._image_label.setPixmap(scaled)
            self._image_label.setVisible(True)
            self._video.setVisible(False)
            self._position.setEnabled(False)
            self._time_label.setText(tr("Image"))
            return
        if os.path.isabs(source) and os.path.exists(source):
            url = QUrl.fromLocalFile(source)
        else:
            url = QUrl(source)
        self._player.setSource(url)
        self._player.play()

    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _toggle_mute(self) -> None:
        muted = not self._audio.isMuted()
        self._audio.setMuted(muted)
        self._refresh_mute_icon()
        self._mute_button.setToolTip(tr("Unmute") if muted else tr("Mute"))

    def _refresh_play_icon(self) -> None:
        theme = current_theme()
        playing = (self._player.playbackState() ==
                   QMediaPlayer.PlaybackState.PlayingState)
        self._play_button.setIcon(icons.icon(
            "pause" if playing else "play", theme.color("text"), theme.px(16)))
        self._play_button.setToolTip(tr("Pause") if playing else tr("Play"))

    def _refresh_mute_icon(self) -> None:
        theme = current_theme()
        muted = self._audio.isMuted()
        self._mute_button.setIcon(icons.icon(
            "mute" if muted else "volume", theme.color("text"), theme.px(16)))

    def _on_playback_state(self, _state) -> None:
        self._refresh_play_icon()

    def _on_position(self, position: int) -> None:
        if not self._seeking:
            self._position.setValue(int(position))
        total = self._player.duration() or int(self._duration() * 1000)
        self._time_label.setText(f"{_format_time(position)} / {_format_time(total)}")

    def _on_duration(self, duration: int) -> None:
        self._position.setRange(0, max(0, int(duration)))

    def _on_seek_start(self) -> None:
        self._seeking = True

    def _on_seek_end(self) -> None:
        self._seeking = False
        self._player.setPosition(self._position.value())

    def _on_seek_move(self, value: int) -> None:
        total = self._player.duration() or int(self._duration() * 1000)
        self._time_label.setText(f"{_format_time(value)} / {_format_time(total)}")

    def _on_media_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._show_error(tr("The preview stream is unavailable. "
                                "You can still download it or open its source page."))

    def _on_player_error(self, _error, error_string: str) -> None:
        log.warning("preview playback failed: %s", error_string)
        self._show_error(tr("This video could not be played here: {error}",
                            error=str(error_string or tr("unknown error"))))

    def _show_error(self, message: str) -> None:
        self._status_label.setObjectName("Error")
        self._status_label.setText(message)
        self._status_label.setVisible(True)
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

    # --------------------------------------------------------------- favourite
    def _read_favorite(self) -> bool:
        try:
            if self._is_media:
                item = self.result
                if item.id is not None:
                    stored = self.ctx.db.get_media(int(item.id))
                    if stored is not None:
                        return bool(stored.is_favorite)
                return bool(item.is_favorite)
            stored = self.ctx.db.get_by_source(self.result.provider, self.result.source_id)
            return bool(stored and stored.is_favorite)
        except Exception:  # noqa: BLE001 - the dialog must still open
            log.exception("could not read favourite state")
            return False

    def _refresh_favorite_button(self) -> None:
        theme = current_theme()
        self._favorite_button.setText(
            tr("In favorites") if self._favorite else tr("Favorite"))
        self._favorite_button.setIcon(icons.icon(
            "star-filled" if self._favorite else "star",
            theme.color("accent") if self._favorite else theme.color("text"),
            theme.px(16)))

    def _toggle_favorite(self) -> None:
        try:
            if self._is_media:
                item = self.result
                if item.id is None:
                    self.ctx.notify(tr("This item is not stored in the database"), "warn")
                    return
                value = not self._favorite
                self.ctx.library.set_favorite(int(item.id), value)
            else:
                stored = self.ctx.db.get_by_source(self.result.provider,
                                                   self.result.source_id)
                if stored is None:
                    self.ctx.library.add_from_search(self.result, favorite=True)
                    value = True
                else:
                    value = not stored.is_favorite
                    self.ctx.library.set_favorite(int(stored.id), value)
        except Exception as error:  # noqa: BLE001
            log.warning("favourite toggle failed: %s", error)
            self.ctx.notify(tr("Could not update favorites: {error}", error=str(error)),
                            "error")
            return
        self._favorite = value
        self._refresh_favorite_button()
        self.ctx.notify(tr("Added to favorites") if value else tr("Removed from favorites"),
                        "ok")

    # ---------------------------------------------------------------- download
    def _on_add_to_library(self) -> None:
        self._start_download(close_after=False)

    def _on_download(self) -> None:
        self._start_download(close_after=True)

    def _start_download(self, close_after: bool) -> None:
        if self._download_started:
            if close_after:
                self.accept()
            return
        try:
            task = self.ctx.downloads.start_download(self._download_result())
        except Exception as error:  # noqa: BLE001
            log.warning("could not start download: %s", error)
            self.ctx.notify(tr("Could not start the download: {error}", error=str(error)),
                            "error")
            self._show_error(tr("Could not start the download: {error}", error=str(error)))
            return
        self._download_started = True
        log.info("preview download started: task %s", getattr(task, "id", "?"))
        for button in (self._add_button, self._download_button):
            if button.isVisible():
                button.setEnabled(False)
                button.setText(tr("Downloading…"))
        self._status_label.setObjectName("Caption")
        self._status_label.setText(tr("Download started - track it on the Downloads page."))
        self._status_label.setVisible(True)
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)
        self.ctx.notify(
            tr("Download started: {title}", title=getattr(self.result, "title", "") or ""),
            "ok")
        if close_after:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(120, self.accept)

    # ------------------------------------------------------------------ source
    def _open_source(self) -> None:
        url = str(getattr(self.result, "page_url", "") or "")
        if url:
            utils.open_url(url)

    # ----------------------------------------------------------------- cleanup
    def _stop_player(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        try:
            self._player.stop()
            self._player.setSource(QUrl())
            self._audio.setMuted(True)
        except Exception:  # noqa: BLE001 - cleanup must never raise
            log.exception("could not stop the preview player")

    def done(self, result: int) -> None:  # noqa: A003 - Qt API
        self._stop_player()
        super().done(result)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._stop_player()
        super().closeEvent(event)


def open_preview(ctx, result: SearchResult | MediaItem,
                 parent: QWidget | None = None) -> int:
    """Create, run and dispose a modal preview dialog. Returns the dialog code."""
    dialog = PreviewDialog(ctx, result, parent)
    try:
        return int(dialog.exec())
    except RuntimeError:  # already deleted by WA_DeleteOnClose
        return 0
    finally:
        try:
            dialog.deleteLater()
        except RuntimeError:
            pass
