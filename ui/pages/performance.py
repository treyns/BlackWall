"""Performance page: modes, real load measurements and auto-pause settings."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from config.constants import (PERFORMANCE_MODES, PERFORMANCE_MODE_ORDER,
                              VIDEO_QUALITY_LABELS, VIDEO_QUALITY_OPTIONS)
from core.i18n import tr
from core.models import PerfSample
from player import decode_info
from ui.components.gauges import MetricGauge
from ui.components.widgets import (
    Card,
    SectionHeader,
    StatTile,
    ToggleSwitch,
    caption,
    dim,
    h2,
    h3,
    text_label,
)
from ui.pages.base import BasePage
from ui.theme import current_theme


class ModeCard(Card):
    def __init__(self, page: "PerformancePage", mode_key: str) -> None:
        super().__init__(object_name="ModeCard")
        self.page = page
        self.mode_key = mode_key
        theme = current_theme()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(theme.px(112))
        data = PERFORMANCE_MODES[mode_key]
        title_row = QHBoxLayout()
        title_row.addWidget(h3(tr(data["label"])))
        title_row.addStretch(1)
        self.fps_badge = QLabel(f"{data['fps']} FPS")
        self.fps_badge.setObjectName("Badge")
        title_row.addWidget(self.fps_badge)
        self.body.addLayout(title_row)
        description = caption(tr(data["description"]))
        description.setWordWrap(True)
        self.body.addWidget(description)
        self.body.addStretch(1)
        self._selected = True

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self.page.select_mode(self.mode_key)
        super().mouseReleaseEvent(event)


class PerformancePage(BasePage):
    PAGE_KEY = "performance"
    TITLE = "Performance"
    SUBTITLE = "Real load and playback modes"

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        theme = self.theme
        self._mode_cards: dict[str, ModeCard] = {}

        self.root.addWidget(SectionHeader(
            tr("Playback mode"), tr("Choose a balance between quality and load")))

        modes_row = QHBoxLayout()
        modes_row.setSpacing(theme.px(14))
        for mode_key in PERFORMANCE_MODE_ORDER:
            card = ModeCard(self, mode_key)
            modes_row.addWidget(card, 1)
            self._mode_cards[mode_key] = card
        self.root.addLayout(modes_row)

        # ------------------------------------------------------------- live metrics
        self.root.addWidget(SectionHeader(
            tr("Measured load"), tr("Real values from this computer, updated every second")))
        metrics = QGridLayout()
        metrics.setSpacing(theme.px(12))
        self._gauges: dict[str, MetricGauge] = {}
        if theme.is_aurora:
            gauge_row = QHBoxLayout()
            gauge_row.setSpacing(theme.px(12))
            for key, title in (
                    ("cpu", tr("CPU · BlackWall")),
                    ("ram", tr("RAM · BlackWall")),
                    ("gpu", tr("GPU · BlackWall")),
                    ("fps", tr("Measured FPS"))):
                box = Card()
                box.setObjectName("MetricCard")
                gauge = MetricGauge(title)
                box.body.addWidget(gauge)
                gauge_row.addWidget(box, 1)
                self._gauges[key] = gauge
            self.root.addLayout(gauge_row)
        else:
            self.tile_cpu = StatTile("performance", tr("CPU · BlackWall"))
            self.tile_ram = StatTile("library", tr("RAM · BlackWall"))
            self.tile_gpu = StatTile("video", tr("GPU · BlackWall"))
            self.tile_fps = StatTile("play", tr("Measured FPS"))
            metrics.addWidget(self.tile_cpu, 0, 0)
            metrics.addWidget(self.tile_ram, 0, 1)
            metrics.addWidget(self.tile_gpu, 0, 2)
            metrics.addWidget(self.tile_fps, 0, 3)
            self.root.addLayout(metrics)
        self.system_line = caption("")
        self.root.addWidget(self.system_line)

        # ----------------------------------------------------------------- limits
        limits = Card()
        limits.body.addWidget(h2(tr("Playback limits")))
        fps_row = QHBoxLayout()
        fps_row.setSpacing(theme.px(12))
        label_box = QVBoxLayout()
        label_box.setSpacing(theme.px(2))
        label_box.addWidget(text_label(tr("FPS limit"), "CardTitle"))
        label_box.addWidget(caption(tr("Lower FPS reduces CPU and GPU load. "
                                       "The limit is applied to decoding and painting.")))
        fps_row.addLayout(label_box, 1)
        self.fps_value = text_label(str(self.ctx.wallpaper.fps_cap), "Value")
        fps_row.addWidget(self.fps_value)
        self.fps_slider = QSlider(Qt.Orientation.Horizontal)
        self.fps_slider.setRange(5, 60)
        self.fps_slider.setSingleStep(5)
        self.fps_slider.setPageStep(5)
        self.fps_slider.setValue(int(self.ctx.wallpaper.fps_cap))
        self.fps_slider.setFixedWidth(theme.px(220))
        self.fps_slider.valueChanged.connect(self._on_fps_slider)
        self.fps_slider.sliderReleased.connect(self._apply_fps)
        fps_row.addWidget(self.fps_slider, 0, Qt.AlignmentFlag.AlignVCenter)
        limits.body.addLayout(fps_row)

        self._toggle_auto = self._make_toggle_row(
            limits.body,
            tr("Automatic pause"),
            tr("Pause wallpapers when they are not visible or the PC is idle"),
            bool(self.ctx.settings.get("performance.auto_pause", True)),
            self._on_auto_pause)
        self._toggle_fullscreen = self._make_toggle_row(
            limits.body,
            tr("Pause in games and fullscreen apps"),
            tr("Detected from the foreground fullscreen window"),
            bool(self.ctx.settings.get("performance.pause_on_fullscreen", True)),
            lambda value: self.ctx.settings.set("performance.pause_on_fullscreen", value))
        self._toggle_idle = self._make_toggle_row(
            limits.body,
            tr("Pause when idle"),
            tr("Pause after the configured time without mouse or keyboard input"),
            bool(self.ctx.settings.get("performance.pause_when_idle", True)),
            lambda value: self.ctx.settings.set("performance.pause_when_idle", value))
        self._toggle_battery = self._make_toggle_row(
            limits.body,
            tr("Pause on battery power"),
            tr("Useful for laptops; has no effect on a desktop PC"),
            bool(self.ctx.settings.get("performance.pause_on_battery", True)),
            lambda value: self.ctx.settings.set("performance.pause_on_battery", value))
        self._toggle_adaptive = self._make_toggle_row(
            limits.body,
            tr("Automatic quality reduction"),
            tr("Lower the FPS and video resolution when the computer is under load; "
               "quality returns automatically after the load drops"),
            bool(self.ctx.settings.get("performance.adaptive_quality", True)),
            self._on_adaptive_toggled)
        self.manual_quality_combo = self._make_quality_row(limits.body)
        self.root.addWidget(limits)

        # ------------------------------------------------------ adaptive quality state
        adaptive_card = Card()
        adaptive_card.body.addWidget(h2(tr("Adaptive quality")))
        quality_row = QHBoxLayout()
        self.quality_label = text_label(tr("Full quality"), "CardTitle")
        quality_row.addWidget(self.quality_label, 1)
        self.quality_badge = QLabel(tr("auto"))
        self.quality_badge.setObjectName("Badge")
        quality_row.addWidget(self.quality_badge)
        adaptive_card.body.addLayout(quality_row)
        self.quality_meta = caption("")
        adaptive_card.body.addWidget(self.quality_meta)
        adaptive_card.body.addWidget(caption(tr(
            "MP4 files have a fixed resolution, so for real resolution reduction "
            "BlackWall prepares a lightweight copy once and reuses it from the cache.")))
        self.root.addWidget(adaptive_card)

        # ----------------------------------------------------------------- decoder
        decoder_card = Card()
        decoder_card.body.addWidget(h2(tr("Video decoding")))
        decoder_row = QHBoxLayout()
        self.decoder_label = text_label(tr("Not measured yet"), "CardTitle")
        decoder_row.addWidget(self.decoder_label, 1)
        self.decoder_badge = QLabel(tr("waiting"))
        self.decoder_badge.setObjectName("BadgeDim")
        decoder_row.addWidget(self.decoder_badge)
        decoder_card.body.addLayout(decoder_row)
        decoder_card.body.addWidget(caption(tr(
            "Hardware decoding is used automatically when the GPU supports the video "
            "format. The state below is read from the real decoder, not assumed.")))
        self.root.addWidget(decoder_card)
        self.root.addStretch(1)

        ctx.performance.sample_ready.connect(self._on_sample)
        ctx.wallpaper.state_changed.connect(self.refresh_mode)
        ctx.wallpaper.adaptive_changed.connect(self._update_adaptive)
        self._decoder_timer = QTimer(self)
        self._decoder_timer.setInterval(1000)
        self._decoder_timer.timeout.connect(self._tick)
        self._decoder_timer.start()
        self.refresh()

    # ------------------------------------------------------------------ helpers
    def _make_toggle_row(self, layout: QVBoxLayout, title: str, description: str,
                         checked: bool, callback) -> ToggleSwitch:
        theme = current_theme()
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, theme.px(4), 0, theme.px(4))
        row_layout.setSpacing(theme.px(12))
        text_box = QVBoxLayout()
        text_box.setSpacing(theme.px(2))
        text_box.addWidget(text_label(title, "CardTitle"))
        description_label = caption(description)
        description_label.setWordWrap(True)
        text_box.addWidget(description_label)
        row_layout.addLayout(text_box, 1)
        toggle = ToggleSwitch()
        toggle.setChecked(checked)
        toggle.toggled.connect(callback)
        row_layout.addWidget(toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(row)
        return toggle

    def _make_quality_row(self, layout: QVBoxLayout) -> QComboBox:
        theme = current_theme()
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, theme.px(4), 0, theme.px(4))
        row_layout.setSpacing(theme.px(12))
        text_box = QVBoxLayout()
        text_box.setSpacing(theme.px(2))
        text_box.addWidget(text_label(tr("Video quality"), "CardTitle"))
        description = caption(tr("Available when automatic quality reduction is disabled"))
        description.setWordWrap(True)
        text_box.addWidget(description)
        row_layout.addLayout(text_box, 1)
        combo = QComboBox()
        for key, label in VIDEO_QUALITY_OPTIONS:
            combo.addItem(tr(label), key)
        current = combo.findData(str(self.ctx.settings.get("playback.manual_quality",
                                                           "original")))
        if current >= 0:
            combo.setCurrentIndex(current)
        combo.setEnabled(False)
        combo.currentIndexChanged.connect(self._on_manual_quality_changed)
        combo.setMinimumWidth(theme.px(150))
        row_layout.addWidget(combo, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(row)
        return combo

    def _manual_quality_enabled(self) -> bool:
        return not bool(self.ctx.settings.get("performance.adaptive_quality", True))

    def _on_manual_quality_changed(self, _index: int) -> None:
        quality = str(self.manual_quality_combo.currentData() or "original")
        self.ctx.settings.set("playback.manual_quality", quality)
        try:
            self.ctx.wallpaper.apply_quality_mode()
        except Exception:  # noqa: BLE001
            pass
        label = tr(VIDEO_QUALITY_LABELS.get(quality, quality))
        self.ctx.notify(tr("Video quality: {quality}", quality=label), "ok")
        self._update_adaptive()

    def _on_fps_slider(self, value: int) -> None:
        self.fps_value.setText(str(value))

    def _apply_fps(self) -> None:
        value = int(self.fps_slider.value())
        self.ctx.wallpaper.set_fps_cap(value)
        self.ctx.notify(tr("FPS limit set to {fps}", fps=value), "ok")

    def _on_auto_pause(self, checked: bool) -> None:
        self.ctx.settings.set("performance.auto_pause", checked)

    def _on_adaptive_toggled(self, checked: bool) -> None:
        self.ctx.settings.set("performance.adaptive_quality", bool(checked))
        if not checked:
            self.ctx.notify(tr("Adaptive quality disabled"), "ok")
        else:
            self.ctx.notify(tr("Adaptive quality enabled"), "ok")
        self._update_adaptive()

    def _tick(self) -> None:
        self._update_decoder()
        self._update_adaptive()

    def _update_adaptive(self) -> None:
        level = self.ctx.wallpaper.adaptive_level
        adaptive_on = bool(self.ctx.settings.get("performance.adaptive_quality", True))
        if not adaptive_on:
            quality = self.ctx.wallpaper.manual_quality
            label = tr(VIDEO_QUALITY_LABELS.get(quality, quality))
            self.quality_label.setText(tr("Video quality: {quality}", quality=label))
            self.quality_label.setObjectName("CardTitle")
            self.quality_badge.setText(tr("manual"))
            self.quality_badge.setObjectName("BadgeDim")
        else:
            labels = {0: tr("Full quality"), 1: tr("Reduced quality"),
                      2: tr("Minimum quality")}
            self.quality_label.setText(labels.get(level, tr("Full quality")))
            self.quality_label.setObjectName("CardTitle")
            if level == 0:
                self.quality_badge.setText(tr("auto"))
                self.quality_badge.setObjectName("Badge")
            else:
                self.quality_badge.setText(tr("reduced"))
                self.quality_badge.setObjectName("Badge")
        pending = ""
        if self.ctx.wallpaper.light_copy_pending():
            if adaptive_on:
                pending = " · " + tr("preparing a lightweight copy…")
            else:
                pending = " · " + tr("preparing the selected video quality…")
        self.quality_meta.setText(
            tr("Effective FPS limit: {fps}", fps=self.ctx.wallpaper.effective_fps_cap)
            + pending)
        for widget in (self.quality_label, self.quality_badge):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self._toggle_adaptive.blockSignals(True)
        self._toggle_adaptive.setChecked(
            bool(self.ctx.settings.get("performance.adaptive_quality", True)))
        self._toggle_adaptive.blockSignals(False)
        combo = self.manual_quality_combo
        combo.blockSignals(True)
        index = combo.findData(str(self.ctx.settings.get("playback.manual_quality",
                                                         "original")))
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.blockSignals(False)
        combo.setEnabled(not adaptive_on)

    # ------------------------------------------------------------------ actions
    def select_mode(self, mode_key: str) -> None:
        self.ctx.wallpaper.set_mode(mode_key)
        self.ctx.settings.set("performance.mode", mode_key)
        self.refresh_mode()
        self.ctx.notify(tr("Performance mode: {mode}",
                           mode=tr(PERFORMANCE_MODES[mode_key]["label"])), "ok")

    def refresh_mode(self) -> None:
        mode = self.ctx.wallpaper.mode
        for key, card in self._mode_cards.items():
            card.set_selected(key == mode)
        fps = int(self.ctx.wallpaper.fps_cap)
        self.fps_slider.blockSignals(True)
        self.fps_slider.setValue(fps)
        self.fps_slider.blockSignals(False)
        self.fps_value.setText(str(fps))

    def refresh(self) -> None:
        self.refresh_mode()
        self._on_sample(self.ctx.performance.latest())
        self._update_decoder()
        self._update_adaptive()

    def on_show(self) -> None:
        self._decoder_timer.start()
        self.refresh()

    def _on_sample(self, sample: PerfSample) -> None:
        if self._gauges:
            self._gauges["cpu"].set_value(sample.cpu, f"{sample.cpu:.0f}%")
            self._gauges["ram"].set_value(
                min(100.0, sample.ram_mb / 1024.0 * 100.0),
                f"{sample.ram_mb:.0f} MB")
            if sample.gpu is None:
                self._gauges["gpu"].set_value(0, tr("n/a"))
            else:
                self._gauges["gpu"].set_value(sample.gpu, f"{sample.gpu:.0f}%")
            if sample.fps > 0:
                self._gauges["fps"].set_value(
                    min(100.0, sample.fps / 60.0 * 100.0), f"{sample.fps:.0f}")
            else:
                self._gauges["fps"].set_value(0, "—")
        else:
            self.tile_cpu.set_value(f"{sample.cpu:.1f}%")
            self.tile_ram.set_value(f"{sample.ram_mb:.0f} MB")
            if sample.gpu is None:
                self.tile_gpu.set_value("n/a")
                self.tile_gpu.title_label.setText(tr("GPU · counter unavailable"))
            else:
                self.tile_gpu.set_value(f"{sample.gpu:.1f}%")
                self.tile_gpu.title_label.setText(tr("GPU · BlackWall"))
            if sample.fps > 0:
                self.tile_fps.set_value(f"{sample.fps:.0f}")
            else:
                self.tile_fps.set_value("—")
        self.system_line.setText(
            tr("Whole system: CPU {cpu:.0f}% · RAM {ram:.0f}%",
               cpu=sample.system_cpu, ram=sample.system_ram))

    def _update_decoder(self) -> None:
        state = decode_info.hardware_active()
        if state is True:
            self.decoder_label.setText(tr("Hardware decoding (GPU)"))
            self.decoder_badge.setText(tr("active"))
            self.decoder_badge.setObjectName("Badge")
            self.decoder_label.setObjectName("CardTitle")
        elif state is False:
            self.decoder_label.setText(tr("Software decoding (CPU)"))
            self.decoder_badge.setText(tr("fallback"))
            self.decoder_badge.setObjectName("BadgeDim")
        else:
            self.decoder_label.setText(tr("Not measured yet"))
            self.decoder_badge.setText(tr("no video playing"))
            self.decoder_badge.setObjectName("BadgeDim")
        for widget in (self.decoder_label, self.decoder_badge):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def on_hide(self) -> None:
        self._decoder_timer.stop()



