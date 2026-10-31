"""Small internal video preview used by the merge-clip list."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl
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
from ui import icons
from ui.components.widgets import caption, h3
from ui.theme import current_theme


class ClipPreviewDialog(QDialog):
    """Plays one clip with a seek bar so the user can identify it visually."""

    def __init__(self, path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = None
        self.path = path
        theme = current_theme()
        self.setWindowTitle(os.path.basename(path))
        self.setModal(True)
        self.resize(theme.px(900), theme.px(600))
        self.setMinimumSize(theme.px(640), theme.px(420))
        root = QVBoxLayout(self)
        root.setContentsMargins(theme.px(16), theme.px(14), theme.px(16), theme.px(14))
        root.setSpacing(theme.px(8))
        root.addWidget(h3(os.path.basename(path)))
        root.addWidget(caption(path))

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setMuted(False)
        self.player.setAudioOutput(self.audio)
        self.video = QVideoWidget(self)
        self.video.setStyleSheet(f"background-color: {theme.color('shadow')};")
        self.player.setVideoOutput(self.video)
        root.addWidget(self.video, 1)

        controls = QHBoxLayout()
        self.play_button = QPushButton()
        self.play_button.setObjectName("IconButton")
        self.play_button.setFixedSize(theme.px(34), theme.px(30))
        self.play_button.setIcon(icons.icon("pause", theme.color("text"), theme.px(15)))
        self.play_button.setToolTip(tr("Pause"))
        self.play_button.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_button)
        self.position = QSlider(Qt.Orientation.Horizontal)
        self.position.setRange(0, 0)
        self.position.sliderPressed.connect(self._seek_start)
        self.position.sliderMoved.connect(self._seek_move)
        self.position.sliderReleased.connect(self._seek_end)
        controls.addWidget(self.position, 1)
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setObjectName("Caption")
        controls.addWidget(self.time_label)
        self.mute_button = QPushButton()
        self.mute_button.setObjectName("IconButton")
        self.mute_button.setFixedSize(theme.px(34), theme.px(30))
        self.mute_button.setToolTip(tr("Mute"))
        self.mute_button.clicked.connect(self._toggle_mute)
        controls.addWidget(self.mute_button)
        close_button = QPushButton(tr("Close"))
        close_button.setObjectName("Ghost")
        close_button.clicked.connect(self.accept)
        controls.addWidget(close_button)
        root.addLayout(controls)

        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.errorOccurred.connect(self._on_error)
        self._seeking = False
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()

    def _toggle_mute(self) -> None:
        self.audio.setMuted(not self.audio.isMuted())
        self.mute_button.setToolTip(tr("Unmute") if self.audio.isMuted() else tr("Mute"))

    def _toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_state(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setIcon(icons.icon("pause" if playing else "play",
                                            current_theme().color("text"),
                                            current_theme().px(15)))
        self.play_button.setToolTip(tr("Pause" if playing else "Play"))

    def _on_duration(self, duration: int) -> None:
        self.position.setRange(0, max(0, duration))
        self._update_time()

    def _on_position(self, position: int) -> None:
        if not self._seeking:
            self.position.setValue(position)
        self._update_time()

    def _update_time(self) -> None:
        total = self.player.duration()
        self.time_label.setText(f"{utils.human_duration(self.position.value() / 1000)} / "
                                f"{utils.human_duration(total / 1000)}")

    def _seek_start(self) -> None:
        self._seeking = True

    def _seek_move(self, value: int) -> None:
        self.player.setPosition(value)

    def _seek_end(self) -> None:
        self._seeking = False
        self.player.setPosition(self.position.value())

    def _on_error(self, _error, message: str) -> None:
        self.time_label.setText(tr("Could not preview this video") + (f": {message}" if message else ""))

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.player.stop()
        super().closeEvent(event)
