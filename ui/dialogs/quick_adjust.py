"""Quick settings dialog for the wallpaper on one monitor."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from config.constants import (
    FIT_MODE_ORDER,
    FIT_MODES,
    VIDEO_QUALITY_OPTIONS,
    VIDEO_QUALITY_WIDTHS,
)
from core.i18n import tr
from core.logger import get_logger
from importers.processing import has_audio_track
from ui.components.widgets import ToggleSwitch, caption, dim, h2, h3, text_label
from ui.theme import current_theme

log = get_logger("quick-adjust")


class QuickAdjustDialog(QDialog):
    """Crop mode, quality cap, FPS cap and audio for one assignment."""

    def __init__(self, ctx, monitor_key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.monitor_key = monitor_key
        self.theme = current_theme()
        self.assignment = ctx.assignment_for(monitor_key)
        self.monitor = ctx.monitors.get(monitor_key)
        self.item = (ctx.library.get(self.assignment.media_id)
                     if self.assignment and self.assignment.media_id else None)
        self.setWindowTitle(tr("Wallpaper settings"))
        self.setModal(True)
        self.setMinimumWidth(self.theme.px(540))
        self.setObjectName("Dialog")
        self._audio_available = False
        self._build()

    # ------------------------------------------------------------------- build
    def _build(self) -> None:
        theme = self.theme
        root = QVBoxLayout(self)
        root.setContentsMargins(theme.px(22), theme.px(20), theme.px(22), theme.px(18))
        root.setSpacing(theme.px(14))

        root.addWidget(h2(tr("Wallpaper settings")))
        if self.monitor is not None:
            root.addWidget(caption(tr("{name} · {resolution} · {refresh:.0f} Hz",
                                       name=self.monitor.name,
                                       resolution=self.monitor.resolution,
                                       refresh=self.monitor.refresh)))
        if self.item is not None:
            root.addWidget(dim(tr("{title} · {resolution}", title=self.item.title,
                                  resolution=self.item.resolution)))

        card = QFrame()
        card.setObjectName("Card")
        body = QVBoxLayout(card)
        body.setContentsMargins(theme.px(16), theme.px(14), theme.px(16), theme.px(14))
        body.setSpacing(theme.px(12))
        root.addWidget(card)

        # ------------------------------------------------------------ crop mode
        body.addWidget(h3(tr("Display mode")))
        self.fit_combo = QComboBox()
        for key in FIT_MODE_ORDER:
            self.fit_combo.addItem(tr(FIT_MODES[key]), key)
        self._select_data(self.fit_combo, self.assignment.fit if self.assignment else "cover")
        body.addWidget(self.fit_combo)

        # -------------------------------------------------------------- quality
        body.addWidget(h3(tr("Video quality")))
        self.quality_combo = QComboBox()
        source_resolution = self.item.resolution if self.item is not None else "—"
        for key, label in VIDEO_QUALITY_OPTIONS:
            text = tr(label)
            if key == "original":
                text = f"{tr('Original')} · {source_resolution}"
            self.quality_combo.addItem(text, key)
        self._select_data(self.quality_combo,
                          self.assignment.quality if self.assignment else "original")
        body.addWidget(self.quality_combo)
        body.addWidget(caption(tr("Quality never goes above the original resolution.")))
        self.automatic_quality = bool(
            self.ctx.settings.get("performance.adaptive_quality", True))
        if self.automatic_quality:
            body.addWidget(caption(tr(
                "Automatic quality reduction is on: manual quality is used when it is off.")))
        body.addWidget(caption(tr("Global FPS limit: {fps}",
                                  fps=self.ctx.wallpaper.effective_fps_cap)))

        # ------------------------------------------------------------------ FPS
        body.addWidget(h3(tr("FPS limit")))
        self.fps_combo = QComboBox()
        self.fps_combo.addItem(tr("Original"), 0)
        for value in (60, 30, 15):
            self.fps_combo.addItem(f"{value} FPS", value)
        self._select_data(self.fps_combo, self.assignment.fps_cap if self.assignment else 0)
        body.addWidget(self.fps_combo)
        body.addWidget(caption(tr("The limit is also capped by the video and monitor refresh rate.")))

        # ---------------------------------------------------------------- sound
        source = ""
        if self.item is not None:
            source = self.item.original_path or self.item.file_path or ""
        if source and self.item is not None and self.item.kind == "video":
            self._audio_available = has_audio_track(source)
        sound_header = QHBoxLayout()
        sound_header.addWidget(h3(tr("Sound")))
        sound_header.addStretch(1)
        self.sound_toggle = ToggleSwitch()
        self.sound_toggle.setChecked(not bool(self.assignment.muted) if self.assignment else False)
        sound_header.addWidget(self.sound_toggle)
        body.addLayout(sound_header)
        self.audio_status = caption(
            tr("This video has no audio track") if not self._audio_available
            else tr("Play the video sound on this monitor"))
        body.addWidget(self.audio_status)

        volume_row = QHBoxLayout()
        volume_row.setSpacing(theme.px(10))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(self.assignment.volume if self.assignment else 0))
        volume_row.addWidget(self.volume_slider, 1)
        self.volume_label = QLabel(f"{self.volume_slider.value()}%")
        volume_row.addWidget(self.volume_label)
        body.addLayout(volume_row)
        self.volume_slider.valueChanged.connect(
            lambda value: self.volume_label.setText(f"{value}%"))
        enabled = self._audio_available
        self.sound_toggle.setEnabled(enabled)
        self.volume_slider.setEnabled(enabled)
        if not enabled:
            self.sound_toggle.setChecked(False)

        # --------------------------------------------------------------- buttons
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(tr("Cancel"))
        cancel.setObjectName("Ghost")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        apply_button = QPushButton(tr("Apply"))
        apply_button.setObjectName("Primary")
        apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_button.clicked.connect(self._apply)
        buttons.addWidget(apply_button)
        root.addLayout(buttons)

    @staticmethod
    def _select_data(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        if index < 0:
            index = 0
        combo.setCurrentIndex(index)

    # ----------------------------------------------------------------- actions
    def _apply(self) -> None:
        if self.assignment is None:
            self.reject()
            return
        self.ctx.set_assignment_fit(self.monitor_key,
                                    str(self.fit_combo.currentData() or "cover"))
        self.ctx.set_assignment_quality(self.monitor_key,
                                        str(self.quality_combo.currentData() or "original"))
        self.ctx.set_assignment_fps(self.monitor_key,
                                    int(self.fps_combo.currentData() or 0))
        if self._audio_available:
            self.ctx.set_assignment_audio(
                self.monitor_key, not self.sound_toggle.isChecked(),
                int(self.volume_slider.value()))
        elif self.assignment.kind != "image":
            self.ctx.set_assignment_audio(self.monitor_key, True, 0)
        self.accept()
