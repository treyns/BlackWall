"""Settings page: all application options with real effects."""
from __future__ import annotations

import os
import platform
import shutil

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import PySide6
from config import paths
from config.constants import (
    ACCENTS_BY_THEME,
    APP_VERSION,
    FIT_MODE_ORDER,
    FIT_MODES,
    IMPORT_MAX_HEIGHTS,
    PERFORMANCE_MODES,
    PERFORMANCE_MODE_ORDER,
    THEMES,
    VIDEO_QUALITY_LABELS,
    VIDEO_QUALITY_OPTIONS,
)
from core import utils
from core.i18n import tr, translator
from core.logger import get_logger
from importers.base import ytdlp_available
from system import autostart
from ui import icons
from ui.components.thumbs import get_service
from ui.components.widgets import (
    Card,
    Divider,
    SectionHeader,
    ToggleSwitch,
    caption,
    h2,
    h3,
    text_label,
)
from ui.pages.base import BasePage
from ui.theme import current_theme

log = get_logger("page.settings")


class SettingsPage(BasePage):
    PAGE_KEY = "settings"
    TITLE = "Settings"
    SUBTITLE = "Application configuration"

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self._provider_status_labels: dict[str, QLabel] = {}
        self._cache_label: QLabel | None = None
        self._free_space_label: QLabel | None = None
        self._sections: list[tuple[str, QWidget, Card]] = []
        self._about_info: QWidget | None = None
        self._build()

    # ------------------------------------------------------------------ helpers
    def _add_section(self, title: str, subtitle: str = "") -> Card:
        header = SectionHeader(tr(title), tr(subtitle) if subtitle else "")
        self.root.addWidget(header)
        card = Card()
        self.root.addWidget(card)
        self._sections.append((title, header, card))
        return card

    def _add_row(self, card: Card, title: str, description: str, control: QWidget) -> None:
        theme = current_theme()
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, theme.px(6), 0, theme.px(6))
        layout.setSpacing(theme.px(14))
        text_box = QVBoxLayout()
        text_box.setSpacing(theme.px(2))
        text_box.addWidget(text_label(tr(title), "CardTitle"))
        if description:
            description_label = caption(tr(description))
            description_label.setWordWrap(True)
            text_box.addWidget(description_label)
        layout.addLayout(text_box, 1)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        if card.body.count():
            card.body.addWidget(Divider())
        card.body.addWidget(row)

    def _toggle(self, checked: bool, callback) -> ToggleSwitch:
        toggle = ToggleSwitch()
        toggle.setChecked(bool(checked))
        toggle.toggled.connect(callback)
        return toggle

    def _combo(self, options: list[tuple[str, str]], current: str, callback) -> QComboBox:
        combo = QComboBox()
        for value, label in options:
            combo.addItem(tr(label), value)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.currentIndexChanged.connect(
            lambda _index: callback(combo.currentData()))
        combo.setMinimumWidth(current_theme().px(190))
        return combo

    def _button(self, text: str, icon_name: str = "", style: str = "Outline") -> QPushButton:
        theme = current_theme()
        button = QPushButton(tr(text))
        button.setObjectName(style)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_name:
            button.setIcon(icons.icon(icon_name, theme.color("text"), theme.px(15)))
        return button

    def _path_row(self, value: str, on_change) -> QWidget:
        theme = current_theme()
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.px(8))
        field = QLineEdit(value)
        field.setReadOnly(True)
        field.setMinimumWidth(theme.px(330))
        field.setCursorPosition(0)
        layout.addWidget(field, 1)
        button = self._button("Change", "folder")
        button.clicked.connect(lambda: on_change(field))
        layout.addWidget(button)
        return holder

    # --------------------------------------------------------------------- build
    def _build(self) -> None:
        theme = current_theme()
        ctx = self.ctx

        # ------------------------------------------------------------------ general
        general = self._add_section("General")
        self._add_row(
            general, "Launch with Windows", "Start BlackWall automatically when you sign in",
            self._toggle(autostart.is_autostart_enabled(), self._on_autostart))
        self._add_row(
            general, "Start minimized", "Launch directly into the system tray",
            self._toggle(bool(ctx.settings.get("general.start_minimized", False)),
                         lambda value: ctx.settings.set("general.start_minimized", value)))
        self._add_row(
            general, "Close to tray", "Keep wallpapers running when the window is closed",
            self._toggle(bool(ctx.settings.get("general.close_to_tray", True)),
                         lambda value: ctx.settings.set("general.close_to_tray", value)))
        languages = [(code, label) for code, label in translator.available_languages()]
        self._add_row(
            general, "Language", "Interface language",
            self._combo(languages, str(ctx.settings.get("general.language", "en")),
                        self._on_language))
        updates_button = self._button("Check for updates", "refresh")
        updates_button.clicked.connect(self._check_updates)
        self._add_row(
            general, "Updates", "This build has no update server configured",
            updates_button)
        self._add_row(
            general, "Restore wallpapers at startup",
            "Re-apply the last wallpaper set when BlackWall starts",
            self._toggle(bool(ctx.settings.get("general.restore_wallpapers", True)),
                         self._on_restore))

        # ---------------------------------------------------------------- appearance
        appearance = self._add_section("Appearance")
        self._add_row(
            appearance, "Theme",
            "Aurora — immersive premium interface; Classic — the original design",
            self._combo([(key, THEMES[key]["label"]) for key in ("aurora", "classic")],
                        current_theme().design, self._on_theme))
        design = current_theme().design
        accent_options = ACCENTS_BY_THEME.get(design, ACCENTS_BY_THEME["classic"])
        self._add_row(
            appearance, "Accent color", "Primary highlight color of the interface",
            self._combo([(key, item["label"]) for key, item in accent_options.items()],
                        current_theme().accent, self._on_accent))
        scale_box = QWidget()
        scale_layout = QHBoxLayout(scale_box)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        scale_layout.setSpacing(theme.px(10))
        self.scale_label = text_label(f"{ctx.settings.get('appearance.ui_scale', 100)}%", "Value")
        scale_layout.addWidget(self.scale_label)
        scale_slider = QSlider(Qt.Orientation.Horizontal)
        scale_slider.setRange(80, 125)
        scale_slider.setSingleStep(5)
        scale_slider.setPageStep(5)
        scale_slider.setValue(int(ctx.settings.get("appearance.ui_scale", 100)))
        scale_slider.setFixedWidth(theme.px(180))
        scale_slider.valueChanged.connect(
            lambda value: self.scale_label.setText(f"{value}%"))
        scale_slider.sliderReleased.connect(
            lambda: self._on_ui_scale(int(scale_slider.value())))
        scale_layout.addWidget(scale_slider, 0, Qt.AlignmentFlag.AlignVCenter)
        self._add_row(appearance, "Interface scale", "Scale all texts and controls",
                      scale_box)
        self._add_row(
            appearance, "Animations", "Animated switches and transitions",
            self._toggle(bool(ctx.settings.get("appearance.animations", True)),
                         self._on_animations))
        self._add_row(
            appearance, "Compact mode", "Tighter spacing for small screens",
            self._toggle(bool(ctx.settings.get("appearance.compact", False)),
                         self._on_compact))

        # ------------------------------------------------------------- performance
        performance = self._add_section("Performance")
        self._add_row(
            performance, "Performance mode", "Preset for FPS target and load",
            self._combo([(key, PERFORMANCE_MODES[key]["label"])
                         for key in PERFORMANCE_MODE_ORDER],
                        ctx.wallpaper.mode, self._on_mode))
        fps_box = QWidget()
        fps_layout = QHBoxLayout(fps_box)
        fps_layout.setContentsMargins(0, 0, 0, 0)
        fps_layout.setSpacing(theme.px(8))
        self.settings_fps = QSpinBox()
        self.settings_fps.setRange(5, 60)
        self.settings_fps.setSingleStep(5)
        self.settings_fps.setValue(int(ctx.settings.get("performance.fps_cap", 30)))
        self.settings_fps.setSuffix(" FPS")
        self.settings_fps.setFixedWidth(theme.px(110))
        self.settings_fps.valueChanged.connect(self._on_fps_cap)
        fps_layout.addWidget(self.settings_fps)
        self._add_row(performance, "FPS limit", "Maximum frames per second", fps_box)
        self._add_row(
            performance, "Hardware decoding",
            "Use GPU video decoding when supported (applies after restart)",
            self._toggle(bool(ctx.settings.get("performance.hardware_decoding", True)),
                         lambda value: ctx.settings.set("performance.hardware_decoding", value)))
        self._add_row(
            performance, "Automatic pause",
            "Pause wallpapers when they are not visible",
            self._toggle(bool(ctx.settings.get("performance.auto_pause", True)),
                         lambda value: ctx.settings.set("performance.auto_pause", value)))
        self._add_row(
            performance, "Automatic quality reduction",
            "Lower the FPS and video resolution when the computer is under load; "
            "quality returns automatically after the load drops",
            self._toggle(bool(ctx.settings.get("performance.adaptive_quality", True)),
                         self._on_adaptive_quality))
        self.manual_quality_combo = self._combo(
            [(key, tr(label)) for key, label in VIDEO_QUALITY_OPTIONS],
            str(ctx.settings.get("playback.manual_quality", "original")),
            self._on_manual_quality)
        self.manual_quality_combo.setEnabled(
            not bool(ctx.settings.get("performance.adaptive_quality", True)))
        self._add_row(
            performance, "Video quality",
            "Available when automatic quality reduction is disabled",
            self.manual_quality_combo)
        open_performance = self._button("Open performance page", "performance")
        open_performance.clicked.connect(lambda: ctx.navigate("performance"))
        self._add_row(performance, "Detailed metrics", "CPU, RAM, GPU and FPS measured live",
                      open_performance)

        # ---------------------------------------------------------------- playback
        playback = self._add_section("Playback")
        volume_box = QWidget()
        volume_layout = QHBoxLayout(volume_box)
        volume_layout.setContentsMargins(0, 0, 0, 0)
        volume_layout.setSpacing(theme.px(10))
        self.volume_label = text_label(f"{int(ctx.settings.get('playback.volume', 0))}%", "Value")
        volume_layout.addWidget(self.volume_label)
        volume_slider = QSlider(Qt.Orientation.Horizontal)
        volume_slider.setRange(0, 100)
        volume_slider.setValue(int(ctx.settings.get("playback.volume", 0)))
        volume_slider.setFixedWidth(theme.px(180))
        volume_slider.valueChanged.connect(
            lambda value: self.volume_label.setText(f"{value}%"))
        volume_slider.sliderReleased.connect(
            lambda: self._on_volume(int(volume_slider.value())))
        volume_layout.addWidget(volume_slider)
        self._add_row(playback, "Volume", "Volume for wallpapers with sound", volume_box)
        self._add_row(
            playback, "Mute", "Silence all wallpaper audio",
            self._toggle(bool(ctx.settings.get("playback.muted", True)),
                         lambda value: ctx.wallpaper.set_muted(value)))
        self._add_row(
            playback, "Loop", "Restart videos automatically",
            self._toggle(bool(ctx.settings.get("playback.loop", True)),
                         lambda value: ctx.wallpaper.set_loop(value)))
        self._add_row(
            playback, "Scaling", "How a wallpaper fills the monitor",
            self._combo([(key, FIT_MODES[key]) for key in FIT_MODE_ORDER],
                        str(ctx.settings.get("playback.fit", "cover")),
                        lambda value: ctx.wallpaper.set_fit(value)))
        quality_combo = self._combo([("original", "Original file (no transcoding)")],
                                    "original", lambda value: None)
        quality_combo.setEnabled(False)
        self._add_row(playback, "Playback quality", "Wallpapers play in their original quality",
                      quality_combo)

        # ------------------------------------------------------------------ import
        import_section = self._add_section("Import by link")
        self._add_row(
            import_section, "Download quality",
            "Maximum video height downloaded from YouTube, TikTok or Pinterest",
            self._combo(
                [(str(height), label) for height, label in IMPORT_MAX_HEIGHTS],
                str(ctx.settings.get("import.max_height", 1080)),
                lambda value: ctx.settings.set("import.max_height", int(value))))
        self._add_row(
            import_section, "Optimize imported videos",
            "Create a monitor-sized copy when the source is larger than the display",
            self._toggle(bool(ctx.settings.get("import.auto_optimize", True)),
                         lambda value: ctx.settings.set("import.auto_optimize", value)))
        self._add_row(
            import_section, "Use the optimized copy",
            "Play the prepared copy while keeping the original file untouched",
            self._toggle(bool(ctx.settings.get("import.prefer_optimized", True)),
                         lambda value: ctx.settings.set("import.prefer_optimized", value)))
        import_button = self._button("Open import page", "link")
        import_button.clicked.connect(lambda: ctx.navigate("import"))
        self._add_row(import_section, "Open import page",
                      "Paste a TikTok, YouTube or Pinterest link", import_button)
        status = tr("yt-dlp is installed") if ytdlp_available() else tr(
            "yt-dlp is not installed; install it with pip")
        import_section.body.addWidget(caption(tr(
            "Only public videos are imported. DRM-protected, private and restricted "
            "videos are not bypassed. Use content you have the rights to. {status}",
            status=status)))

        # ----------------------------------------------------------------- storage
        storage = self._add_section("Storage")

        def change_library(field: QLineEdit) -> None:
            folder = QFileDialog.getExistingDirectory(self, tr("Choose library folder"),
                                                      field.text())
            if folder:
                self.ctx.settings.set("storage.library_dir", folder)
                field.setText(folder)

        def change_downloads(field: QLineEdit) -> None:
            folder = QFileDialog.getExistingDirectory(self, tr("Choose downloads folder"),
                                                      field.text())
            if folder:
                self.ctx.settings.set("storage.download_dir", folder)
                field.setText(folder)

        self._add_row(
            storage, "Library folder", "Default folder for wallpapers",
            self._path_row(str(ctx.settings.get("storage.library_dir", "")),
                           change_library))
        self._add_row(
            storage, "Downloads folder", "Where downloaded wallpapers are saved",
            self._path_row(str(ctx.settings.get("storage.download_dir", "")),
                           change_downloads))

        cache_size = utils.human_size(utils.dir_size_bytes(paths.CACHE_DIR))
        self._cache_label = text_label(tr("Thumbnail cache: {size}", size=cache_size),
                                       "CardMeta")
        cache_box = QWidget()
        cache_layout = QHBoxLayout(cache_box)
        cache_layout.setContentsMargins(0, 0, 0, 0)
        cache_layout.setSpacing(theme.px(10))
        cache_layout.addWidget(self._cache_label)
        clear_cache_button = self._button("Clear thumbnails", "trash")
        clear_cache_button.clicked.connect(self._clear_cache)
        cache_layout.addWidget(clear_cache_button)
        self._add_row(storage, "Cache", "Cached previews can be regenerated at any time",
                      cache_box)
        self._free_space_label = text_label(
            tr("Free disk space: {space:.1f} GB", space=utils.free_space_gb(
                str(ctx.settings.get("storage.download_dir", "")))), "CardMeta")
        self._add_row(storage, "Disk space", "Free space available for downloads",
                      self._free_space_label)

        # --------------------------------------------------------------- providers
        providers = self._add_section(
            "Wallpaper sources",
            "API keys are stored locally in data/settings.json and never in the source code")
        for provider, label in (("pixabay", "Pixabay"), ("pexels", "Pexels")):
            box = QWidget()
            layout = QHBoxLayout(box)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(theme.px(8))
            field = QLineEdit(str(ctx.settings.get(f"providers.{provider}_key", "")))
            field.setPlaceholderText(tr("Paste {provider} API key", provider=label))
            field.setMinimumWidth(theme.px(300))
            field.setEchoMode(QLineEdit.EchoMode.Password)
            layout.addWidget(field, 1)
            status = QLabel()
            self._provider_status_labels[provider] = status
            layout.addWidget(status)
            get_key = self._button("Get key", "external")
            from config.constants import PROVIDERS

            get_key.clicked.connect(
                lambda _=False, url=PROVIDERS[provider]["api_docs"]: utils.open_url(url))
            layout.addWidget(get_key)
            save_key = self._button("Save", "check", "Primary")
            save_key.clicked.connect(
                lambda _=False, name=provider, edit=field: self._save_provider_key(name, edit))
            layout.addWidget(save_key)
            self._add_row(providers, f"{label} API key",
                          PROVIDERS[provider]["key_help"], box)
            self._add_row(
                providers, f"Enable {label}", "Use this source for search",
                self._toggle(bool(ctx.settings.get(f"providers.{provider}_enabled", True)),
                             lambda value, name=provider:
                             self._on_provider_enabled(name, value)))
        self._refresh_provider_status()

        about_button = self._button("Open data folder", "folder")
        about_button.clicked.connect(
            lambda: utils.open_in_explorer(str(paths.DATA_DIR)))
        self._add_row(self._add_section("About"), "Version", f"BlackWall {APP_VERSION}",
                      about_button)
        info = caption(
            tr("Python {python} · Qt {qt} · PySide6 {pyside}", python=platform.python_version(),
               qt=__import__("PySide6.QtCore", fromlist=["qVersion"]).qVersion(),
               pyside=PySide6.__version__))
        self._about_info = info
        self.root.addWidget(info)
        self.root.addStretch(1)
        if self.theme.is_aurora:
            self._build_aurora_categories()

    def _build_aurora_categories(self) -> None:
        """Aurora settings: categories on the left, scrollable content on the right."""
        theme = current_theme()
        groups = [
            ("General", ("General",)),
            ("Appearance", ("Appearance",)),
            ("Performance", ("Performance",)),
            ("Playback", ("Playback",)),
            ("Storage", ("Storage",)),
            ("Sources", ("Import by link", "Wallpaper sources")),
            ("About", ("About",)),
        ]
        sections_by_title = {title: (header, card)
                             for title, header, card in self._sections}
        while self.root.count():
            self.root.takeAt(0)

        body = QHBoxLayout()
        body.setSpacing(theme.px(18))
        nav = QWidget()
        nav.setObjectName("SettingsNav")
        nav.setFixedWidth(theme.px(200))
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(theme.px(8), theme.px(4),
                                      theme.px(8), theme.px(4))
        nav_layout.setSpacing(theme.px(4))
        nav_layout.addWidget(h3(tr("Settings")))
        nav_layout.addSpacing(theme.px(8))

        stack = QStackedWidget()
        buttons: list[QPushButton] = []
        for label, titles in groups:
            content = QWidget()
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(0, 0, theme.px(8), 0)
            content_layout.setSpacing(theme.px(14))
            for title in titles:
                section = sections_by_title.get(title)
                if section is None:
                    continue
                header, card = section
                content_layout.addWidget(header)
                content_layout.addWidget(card)
            if label == "About" and self._about_info is not None:
                content_layout.addWidget(self._about_info)
            content_layout.addStretch(1)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(content)
            stack.addWidget(scroll)

            button = QPushButton(tr(label))
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, index=len(buttons): self._select_category(
                    stack, buttons, index))
            buttons.append(button)
            nav_layout.addWidget(button)
        nav_layout.addStretch(1)
        if buttons:
            buttons[0].setChecked(True)
            stack.setCurrentIndex(0)
        body.addWidget(nav)
        body.addWidget(stack, 1)
        self.root.addLayout(body)

    def _select_category(self, stack: QStackedWidget,
                         buttons: list[QPushButton], index: int) -> None:
        stack.setCurrentIndex(index)
        for i, button in enumerate(buttons):
            button.setChecked(i == index)

    # ------------------------------------------------------------------- actions
    def _on_autostart(self, value: bool) -> None:
        result = autostart.set_autostart(bool(value))
        if result != bool(value):
            self.ctx.notify(tr("Could not change the Windows autostart entry"), "error")
        else:
            self.ctx.settings.set("general.run_at_startup", bool(value))
            self.ctx.notify(
                tr("Autostart enabled") if value else tr("Autostart disabled"), "ok")

    def _on_language(self, code: str) -> None:
        self.ctx.settings.set("general.language", code)
        QTimer.singleShot(0, lambda: self.ctx.main_window.apply_language(code))

    def _on_restore(self, value: bool) -> None:
        self.ctx.settings.set("general.restore_wallpapers", bool(value))
        if value:
            self.ctx.wallpaper.refresh()

    def _on_theme(self, value: str) -> None:
        if value not in THEMES:
            return
        old_design = current_theme().design
        old_accent = str(self.ctx.settings.get("appearance.accent", ""))
        self.ctx.settings.set(f"appearance.{old_design}_accent", old_accent)
        accents = ACCENTS_BY_THEME[value]
        saved = str(self.ctx.settings.get(f"appearance.{value}_accent", "") or "")
        accent = saved if saved in accents else next(iter(accents))
        self.ctx.settings.set("appearance.accent", accent)
        self.ctx.settings.set(f"appearance.{value}_accent", accent)
        self.ctx.settings.set("appearance.theme", value)
        QTimer.singleShot(0, self.ctx.main_window.apply_theme)

    def _on_accent(self, value: str) -> None:
        design = current_theme().design
        self.ctx.settings.set("appearance.accent", value)
        self.ctx.settings.set(f"appearance.{design}_accent", value)
        QTimer.singleShot(0, self.ctx.main_window.apply_theme)

    def _on_ui_scale(self, value: int) -> None:
        self.ctx.settings.set("appearance.ui_scale", int(value))
        QTimer.singleShot(0, self.ctx.main_window.apply_theme)

    def _on_animations(self, value: bool) -> None:
        self.ctx.settings.set("appearance.animations", bool(value))
        QTimer.singleShot(0, self.ctx.main_window.apply_theme)

    def _on_compact(self, value: bool) -> None:
        self.ctx.settings.set("appearance.compact", bool(value))
        QTimer.singleShot(0, self.ctx.main_window.apply_theme)

    def _on_mode(self, mode: str) -> None:
        self.ctx.wallpaper.set_mode(mode)
        self.ctx.settings.set("performance.mode", mode)
        self.settings_fps.blockSignals(True)
        self.settings_fps.setValue(int(self.ctx.wallpaper.fps_cap))
        self.settings_fps.blockSignals(False)

    def _on_fps_cap(self, value: int) -> None:
        self.ctx.wallpaper.set_fps_cap(int(value))

    def _on_volume(self, value: int) -> None:
        self.ctx.wallpaper.set_volume(int(value))
        self.ctx.wallpaper.set_muted(False)

    def _on_provider_enabled(self, provider: str, value: bool) -> None:
        self.ctx.settings.set(f"providers.{provider}_enabled", bool(value))
        self.ctx.search.reload_providers()
        self._refresh_provider_status()

    def _save_provider_key(self, provider: str, field: QLineEdit) -> None:
        key = field.text().strip()
        self.ctx.settings.set(f"providers.{provider}_key", key)
        self.ctx.search.reload_providers()
        self._refresh_provider_status()
        self.ctx.notify(tr("{provider} API key saved", provider=provider.title()), "ok")

    def _refresh_provider_status(self) -> None:
        for provider, label in self._provider_status_labels.items():
            has_key = bool(self.ctx.settings.api_key(provider))
            label.setText(tr("Configured") if has_key else tr("Not set"))
            label.setObjectName("Badge" if has_key else "BadgeDim")
            label.style().unpolish(label)
            label.style().polish(label)

    def _clear_cache(self) -> None:
        service = get_service()
        service.clear_cache()
        try:
            self.ctx.wallpaper.clear_quality_cache()
        except Exception:  # noqa: BLE001
            pass
        size = utils.human_size(utils.dir_size_bytes(paths.CACHE_DIR))
        if self._cache_label is not None:
            self._cache_label.setText(tr("Thumbnail cache: {size}", size=size))
        self.ctx.notify(tr("Thumbnail cache cleared"), "ok")

    def on_show(self) -> None:
        # The adaptive quality toggle can also be changed on the Performance
        # page, so keep the manual quality row in sync when Settings is opened.
        self._sync_quality_controls()

    def _sync_quality_controls(self) -> None:
        combo = getattr(self, "manual_quality_combo", None)
        if combo is None:
            return
        adaptive = bool(self.ctx.settings.get("performance.adaptive_quality", True))
        combo.blockSignals(True)
        index = combo.findData(str(self.ctx.settings.get("playback.manual_quality",
                                                         "original")))
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.blockSignals(False)
        combo.setEnabled(not adaptive)

    def _on_adaptive_quality(self, value: bool) -> None:
        self.ctx.settings.set("performance.adaptive_quality", bool(value))
        if hasattr(self, "manual_quality_combo"):
            self.manual_quality_combo.setEnabled(not bool(value))
        if not value:
            self.ctx.notify(tr("Adaptive quality disabled"), "ok")
        else:
            self.ctx.notify(tr("Adaptive quality enabled"), "ok")

    def _on_manual_quality(self, quality: str) -> None:
        self.ctx.settings.set("playback.manual_quality", quality)
        try:
            self.ctx.wallpaper.apply_quality_mode()
        except Exception:  # noqa: BLE001
            pass
        label = tr(VIDEO_QUALITY_LABELS.get(quality, quality))
        self.ctx.notify(tr("Video quality: {quality}", quality=label), "ok")

    def _check_updates(self) -> None:
        QMessageBox.information(
            self, tr("Check for updates"),
            tr("This build is not connected to an update server. "
               "Current version: {version}.", version=APP_VERSION))

