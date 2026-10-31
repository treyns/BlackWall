"""Home page: current wallpaper, quick actions, stats and recent wallpapers."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config.constants import PERFORMANCE_MODES
from core.i18n import tr
from core.logger import get_logger
from core.models import MediaItem
from core.utils import human_duration
from ui import icons
from ui.components.thumbs import ThumbnailWidget
from ui.components.widgets import (
    Badge,
    Card,
    EmptyState,
    SectionHeader,
    StatTile,
    caption,
    dim,
    h2,
    h3,
    text_label,
)
from ui.pages.base import BasePage
from ui.theme import current_theme

log = get_logger("page.home")


class RecentCard(QWidget):
    def __init__(self, item: MediaItem, on_click, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self._item = item
        self._on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(theme.px(206))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.px(7))
        self.thumb = ThumbnailWidget(206, 116)
        layout.addWidget(self.thumb)
        title = text_label(item.title or tr("Untitled"), "CardTitle")
        title.setFixedWidth(theme.px(206))
        layout.addWidget(title)
        self.meta = text_label(
            " · ".join(part for part in (item.resolution, human_duration(item.duration)) if part),
            "CardMeta")
        layout.addWidget(self.meta)
        self.setToolTip(tr("Install {title}", title=item.title))
        self.thumb.set_source(item.file_path or "", key=f"media:{item.id}")

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self._item)
        super().mouseReleaseEvent(event)


class HomePage(BasePage):
    PAGE_KEY = "home"
    TITLE = "Welcome to BlackWall"
    SUBTITLE = "Create the atmosphere of your desktop"

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        theme = self.theme
        self._selected_monitor = None

        # ------------------------------------------------------- current wallpaper
        top_row = QHBoxLayout()
        top_row.setSpacing(theme.px(18))

        self.current_card = Card()
        self.current_card.setMinimumWidth(theme.px(520))
        header = QHBoxLayout()
        header.setSpacing(theme.px(8))
        header.addWidget(h2(tr("Current wallpaper")))
        header.addStretch(1)
        self.state_badge = Badge(tr("No wallpaper"), accent=False)
        header.addWidget(self.state_badge)
        self.current_card.body.addLayout(header)

        self.monitor_bar = QHBoxLayout()
        self.monitor_bar.setSpacing(theme.px(6))
        self.current_card.body.addLayout(self.monitor_bar)

        self.preview_holder = QWidget()
        preview_layout = QVBoxLayout(self.preview_holder)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview = ThumbnailWidget(560, 300)
        self.preview.setFixedHeight(300)
        self.preview.setMinimumWidth(320)
        self.preview.setMaximumWidth(16777215)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        preview_layout.addWidget(self.preview)
        self.preview_empty = EmptyState(
            "image", tr("No wallpaper assigned"),
            tr("Choose a video or picture and it will appear behind your desktop icons."),
            tr("Find wallpapers"))
        self.preview_empty.action_clicked.connect(lambda: self.ctx.navigate("discover"))
        preview_layout.addWidget(self.preview_empty)
        self.current_card.body.addWidget(self.preview_holder)

        self.wallpaper_title = h3(tr("—"))
        self.current_card.body.addWidget(self.wallpaper_title)
        self.wallpaper_meta = dim("")
        self.current_card.body.addWidget(self.wallpaper_meta)

        actions = QHBoxLayout()
        actions.setSpacing(theme.px(8))
        self.change_button = QPushButton(tr("Change"))
        self.change_button.setObjectName("Primary")
        self.change_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change_button.clicked.connect(lambda: self.ctx.navigate("library"))
        self.pause_button = QPushButton(tr("Pause"))
        self.pause_button.setObjectName("Outline")
        self.pause_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_button.setToolTip(tr("Pause or resume this monitor"))
        self.pause_button.clicked.connect(self._toggle_pause)
        self.adjust_button = QPushButton(tr("Adjust"))
        self.adjust_button.setObjectName("Outline")
        self.adjust_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.adjust_button.clicked.connect(self._open_quick_adjust)
        actions.addWidget(self.change_button)
        actions.addWidget(self.pause_button)
        actions.addWidget(self.adjust_button)
        actions.addStretch(1)
        self._actions_layout = actions
        self.current_card.body.addLayout(actions)
        top_row.addWidget(self.current_card, 3)

        # ----------------------------------------------------------------- stats
        stats_card = Card()
        stats_card.setMinimumWidth(theme.px(330))
        stats_card.body.addWidget(h2(tr("At a glance")))
        grid = QGridLayout()
        grid.setSpacing(theme.px(10))
        self.tile_library = StatTile("library", tr("Wallpapers in library"))
        self.tile_monitors = StatTile("monitors", tr("Active monitors"))
        self.tile_mode = StatTile("performance", tr("Performance mode"))
        self.tile_playback = StatTile("play", tr("Playback"))
        grid.addWidget(self.tile_library, 0, 0)
        grid.addWidget(self.tile_monitors, 0, 1)
        grid.addWidget(self.tile_mode, 1, 0)
        grid.addWidget(self.tile_playback, 1, 1)
        stats_card.body.addLayout(grid)
        stats_card.body.addStretch(1)
        self.fps_line = caption("")
        stats_card.body.addWidget(self.fps_line)
        top_row.addWidget(stats_card, 3)
        self.root.addLayout(top_row)

        # ---------------------------------------------------------- quick actions
        self.root.addWidget(SectionHeader(tr("Quick actions")))
        quick = Card()
        quick_row = QHBoxLayout()
        quick_row.setSpacing(theme.px(10))
        quick_actions = [
            ("discover", "Find wallpapers"),
            ("plus", "Add video"),
            ("library", "Open library"),
            ("monitors", "Configure monitors"),
        ]
        for icon_name, label in quick_actions:
            button = QPushButton(tr(label))
            button.setObjectName("Outline")
            button.setIcon(icons.icon(icon_name, theme.color("text"), theme.px(18)))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(theme.px(46))
            if label == "Find wallpapers":
                button.clicked.connect(lambda: self.ctx.navigate("discover"))
            elif label == "Add video":
                button.clicked.connect(self._add_video)
            elif label == "Open library":
                button.clicked.connect(lambda: self.ctx.navigate("library"))
            else:
                button.clicked.connect(lambda: self.ctx.navigate("monitors"))
            quick_row.addWidget(button, 1)
        quick.body.addLayout(quick_row)
        self.root.addWidget(quick)

        # ------------------------------------------------------------- recently used
        self.recent_header = SectionHeader(tr("Recently used"))
        self.root.addWidget(self.recent_header)
        self.recent_row = QHBoxLayout()
        self.recent_row.setSpacing(theme.px(14))
        self.recent_row.addStretch(1)
        self.root.addLayout(self.recent_row)
        self.recent_placeholder = dim(tr("Wallpapers you install will appear here."))
        self.root.addWidget(self.recent_placeholder)
        self.root.addStretch(1)

        if self.theme.is_aurora:
            self._arrange_aurora_hero()

        # ---------------------------------------------------------------- signals
        ctx.assignments_changed.connect(self.refresh)
        ctx.library.changed.connect(self.refresh)
        ctx.monitors.changed.connect(self.refresh)
        ctx.wallpaper.state_changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------ actions
    def _arrange_aurora_hero(self) -> None:
        """Turn the current-wallpaper card into a large cinematic hero block."""
        theme = self.theme
        self.current_card.setObjectName("HeroCard")
        self.current_card.setMinimumWidth(theme.px(560))
        self.preview.setFixedHeight(theme.px(360))
        self.wallpaper_title.setObjectName("H2")

        body = self.current_card.body
        for index in reversed(range(body.count())):
            item = body.itemAt(index)
            if (item.widget() in (self.wallpaper_title, self.wallpaper_meta)
                    or item.layout() is self._actions_layout):
                body.takeAt(index)

        old_layout = self.preview_holder.layout()
        if old_layout is not None:
            while old_layout.count():
                old_layout.takeAt(0)

        body_index = body.indexOf(self.preview_holder)
        if body_index >= 0:
            body.takeAt(body_index)
        old_holder = self.preview_holder
        stage = QWidget()
        stage.setObjectName("HeroStage")
        stage.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        grid = QGridLayout(stage)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        grid.addWidget(self.preview_empty, 0, 0)
        grid.addWidget(self.preview, 0, 0)

        self.hero_overlay = QFrame()
        self.hero_overlay.setObjectName("HeroOverlay")
        overlay = QVBoxLayout(self.hero_overlay)
        overlay.setContentsMargins(theme.px(18), theme.px(14),
                                   theme.px(18), theme.px(14))
        overlay.setSpacing(theme.px(4))
        top_line = QHBoxLayout()
        self.hero_fps = Badge("", accent=True)
        top_line.addWidget(self.wallpaper_title, 1)
        top_line.addWidget(self.hero_fps, 0, Qt.AlignmentFlag.AlignTop)
        overlay.addLayout(top_line)
        overlay.addWidget(self.wallpaper_meta)
        overlay.addSpacing(theme.px(6))
        overlay.addLayout(self._actions_layout)
        grid.addWidget(self.hero_overlay, 0, 0, Qt.AlignmentFlag.AlignBottom)
        self.hero_overlay.hide()
        if body_index >= 0:
            body.insertWidget(body_index, stage)
        else:
            body.addWidget(stage)
        self.preview_holder = stage
        old_holder.deleteLater()

    def _toggle_pause(self) -> None:
        monitor = self._monitor_for_current()
        if monitor is None:
            return
        self.ctx.toggle_monitor_paused(monitor.key)
        self.refresh()

    def _add_video(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("Add wallpapers"),
            str(self.ctx.library.library_dir()),
            tr("Wallpapers") + " (*.mp4 *.webm *.mkv *.mov *.m4v *.gif *.webp *.jpg *.jpeg *.png);;"
            + tr("All files") + " (*.*)")
        if not files:
            return
        ids, errors = self.ctx.library.import_files(files)
        if ids:
            self.ctx.notify(tr("{count} wallpaper(s) added to the library", count=len(ids)), "ok")
            self.ctx.install_media(ids[0], None)
            self.refresh()
        if errors:
            QMessageBox.warning(self, tr("Some files were skipped"), "\n".join(errors[:6]))

    # ------------------------------------------------------------------ helpers
    def _monitor_for_current(self):
        monitors = self.ctx.monitors.monitors()
        if self._selected_monitor:
            for monitor in monitors:
                if monitor.key == self._selected_monitor:
                    return monitor
        return self.ctx.monitors.primary()

    def _select_monitor(self, key: str) -> None:
        self._selected_monitor = key
        self.refresh()

    def _install_recent(self, item: MediaItem) -> None:
        if item.id is not None:
            self.ctx.install_media(item.id, None)
            self.refresh()

    def _open_quick_adjust(self) -> None:
        monitor = self._monitor_for_current()
        if monitor is None or self.ctx.assignment_for(monitor.key) is None:
            return
        from ui.dialogs.quick_adjust import QuickAdjustDialog

        dialog = QuickAdjustDialog(self.ctx, monitor.key, self)
        if dialog.exec():
            self.refresh()

    # ------------------------------------------------------------------- refresh
    def refresh(self) -> None:
        monitors = self.ctx.monitors.monitors()

        # monitor selector chips
        while self.monitor_bar.count():
            child = self.monitor_bar.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        for monitor in monitors:
            button = QPushButton(
                tr("{name} · {res}", name=monitor.name, res=monitor.resolution))
            button.setObjectName("Chip")
            button.setCheckable(True)
            button.setChecked(monitor is self._monitor_for_current())
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, key=monitor.key: self._select_monitor(key))
            self.monitor_bar.addWidget(button)
        self.monitor_bar.addStretch(1)

        monitor = self._monitor_for_current()
        assignment = self.ctx.assignment_for(monitor.key) if monitor is not None else None
        item = (self.ctx.library.get(assignment.media_id)
                if assignment and assignment.media_id else None)

        has_wallpaper = bool(assignment and assignment.file_path)
        self.preview.setVisible(has_wallpaper)
        self.preview_empty.setVisible(not has_wallpaper)
        self.wallpaper_title.setVisible(has_wallpaper)
        self.wallpaper_meta.setVisible(has_wallpaper)
        self.change_button.setVisible(has_wallpaper)
        self.pause_button.setVisible(has_wallpaper)
        self.adjust_button.setVisible(has_wallpaper)
        if hasattr(self, "hero_overlay"):
            self.hero_overlay.setVisible(has_wallpaper)

        paused = self.ctx.wallpaper.monitor_paused(monitor.key) if monitor else False
        status_text = tr(self.ctx.wallpaper.status_text(monitor.key if monitor else None))
        self.pause_button.setText(tr("Resume") if paused else tr("Pause"))

        if has_wallpaper:
            source = assignment.file_path
            self.preview.set_source(source, key=f"assign:{assignment.media_id or source}")
            title = item.title if item is not None else (assignment.title or tr("Untitled"))
            self.wallpaper_title.setText(title)
            parts: list[str] = []
            if item is not None:
                parts.append(item.resolution)
                if item.format:
                    parts.append(str(item.format).upper())
                if item.duration:
                    parts.append(human_duration(item.duration))
            if monitor is not None:
                parts.append(monitor.name)
            parts.append(status_text)
            self.wallpaper_meta.setText(" · ".join(part for part in parts if part))
            self.state_badge.setText(status_text)
            self.state_badge.setObjectName(
                "BadgeDim" if (paused or self.ctx.wallpaper.auto_paused) else "Badge")
        else:
            self.state_badge.setText(tr("No wallpaper"))
            self.state_badge.setObjectName("BadgeDim")
        self.state_badge.style().unpolish(self.state_badge)
        self.state_badge.style().polish(self.state_badge)

        # stats
        stats = self.ctx.library.stats()
        active_monitors = sum(
            1 for value in self.ctx.wallpaper.assignments().values() if value.enabled)
        mode = self.ctx.wallpaper.mode
        mode_label = tr(PERFORMANCE_MODES.get(mode, PERFORMANCE_MODES["balanced"])["label"])
        self.tile_library.set_value(str(stats.get("library", 0)))
        self.tile_monitors.set_value(tr("{n} of {total}", n=active_monitors, total=len(monitors)))
        self.tile_mode.set_value(mode_label)
        self.tile_playback.set_value(status_text)
        fps = self.ctx.wallpaper.measured_fps()
        if fps > 0:
            self.fps_line.setText(tr("Measured playback: {fps} FPS", fps=f"{fps:.0f}"))
            if hasattr(self, "hero_fps"):
                self.hero_fps.setText(f"{fps:.0f} FPS")
        else:
            self.fps_line.setText(tr("Playback is not measured while paused"))
            if hasattr(self, "hero_fps"):
                self.hero_fps.setText(tr("Paused") if paused else "")
        if hasattr(self, "hero_fps"):
            self.hero_fps.setVisible(bool(self.hero_fps.text()))

        # recently used
        while self.recent_row.count():
            child = self.recent_row.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        recent = self.ctx.library.recent(5)
        visible = 0
        for item in recent:
            if not item.file_path:
                continue
            if visible >= 4:
                break
            card = RecentCard(item, self._install_recent)
            self.recent_row.addWidget(card)
            visible += 1
        self.recent_row.addStretch(1)
        self.recent_placeholder.setVisible(visible == 0)

    def on_show(self) -> None:
        self.refresh()



