"""My Library page: every local / downloaded wallpaper in a live gallery."""
from __future__ import annotations

import os

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QWidget,
)

from config.constants import FIT_MODE_ORDER, FIT_MODES
from core import utils
from core.i18n import tr
from core.logger import get_logger
from core.models import MediaItem
from library.ui_helpers import (
    CompactCard,
    LibraryCard,
    TwoActionEmptyState,
    confirm_remove,
    item_is_local,
    open_media_preview,
    show_install_menu,
)
from ui import icons
from ui.components.flow import FlowLayout
from ui.components.widgets import ChipBar, SegmentedControl, dim
from ui.pages.base import BasePage
from ui.theme import current_theme

log = get_logger("page.library")

SORT_OPTIONS: list[tuple[str, str]] = [
    ("added", "Recently added"),
    ("title", "Title"),
    ("resolution", "Resolution"),
    ("duration", "Duration"),
]

KIND_CHIPS: list[tuple[str, str]] = [
    ("all", "All"),
    ("video", "Video"),
    ("animation", "Animated"),
    ("image", "Image"),
]

ADD_FILE_FILTER = (
    tr("Videos") + " (*.mp4 *.webm *.mkv *.mov)"
    + ";;" + tr("Animated") + " (*.gif *.webp)"
    + ";;" + tr("Images") + " (*.jpg *.jpeg *.png)"
    + ";;" + tr("All supported media")
    + " (*.mp4 *.webm *.mkv *.mov *.gif *.webp *.jpg *.jpeg *.png)"
)


def _plural_wallpapers(count: int) -> str:
    if count == 1:
        return tr("1 wallpaper")
    return tr("{count} wallpapers", count=count)


class LibraryPage(BasePage):
    PAGE_KEY = "library"
    TITLE = "My Library"
    SUBTITLE = "Your local wallpaper collection"

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self._view_mode = "grid"
        self._signature: tuple | None = None
        self._cards: list[LibraryCard | CompactCard] = []
        self._items: list[MediaItem] = []
        self._refresh_pending = False
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self.refresh)
        self._build()
        self._connect()
        self.refresh()

    # ------------------------------------------------------------------- build
    def _build(self) -> None:
        theme = self.theme
        self.root.setSpacing(theme.px(14))

        # ---------------------------------------------------------------- toolbar
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(theme.px(10))

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search library"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(theme.px(180))
        self.search.addAction(icons.icon("search", theme.color("text_dim"), theme.px(16)),
                              QLineEdit.ActionPosition.LeadingPosition)
        toolbar_layout.addWidget(self.search, 1)

        self.sort_combo = QComboBox()
        for key, label in SORT_OPTIONS:
            self.sort_combo.addItem(tr(label), key)
        self.sort_combo.setMinimumWidth(theme.px(150))
        self.sort_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sort_combo.setToolTip(tr("Sort library"))
        toolbar_layout.addWidget(self.sort_combo)

        self.view_toggle = SegmentedControl(
            [("grid", tr("Grid")), ("compact", tr("Compact"))], "grid")
        self.view_toggle.setToolTip(tr("Switch between grid and compact view"))
        toolbar_layout.addWidget(self.view_toggle)

        self.import_button = QPushButton(tr("Import by link"))
        self.import_button.setObjectName("Outline")
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_button.setIcon(icons.icon("link", theme.color("text"), theme.px(16)))
        self.import_button.setToolTip(tr("Import a TikTok, YouTube or Pinterest video"))
        toolbar_layout.addWidget(self.import_button)

        self.merge_button = QPushButton(tr("Merge videos"))
        self.merge_button.setObjectName("Outline")
        self.merge_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.merge_button.setIcon(icons.icon("video", theme.color("text"), theme.px(16)))
        self.merge_button.setToolTip(tr("Combine several videos into one wallpaper"))
        toolbar_layout.addWidget(self.merge_button)

        self.add_button = QPushButton(tr("Add files"))
        self.add_button.setObjectName("Primary")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.setIcon(icons.icon("plus", theme.color("accent_text"), theme.px(16)))
        self.add_button.setToolTip(tr("Add local videos or wallpapers to your library"))
        toolbar_layout.addWidget(self.add_button)
        self.root.addWidget(toolbar)

        # ---------------------------------------------------------------- filters
        filter_row = QWidget()
        filter_layout = QHBoxLayout(filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(theme.px(10))
        self.chips = ChipBar([(key, tr(label)) for key, label in KIND_CHIPS])
        filter_layout.addWidget(self.chips, 1)
        self.count_label = dim("")
        filter_layout.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.root.addWidget(filter_row)

        # ----------------------------------------------------------------- gallery
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.gallery = QWidget()
        self.flow = FlowLayout(self.gallery, margin=0, spacing=theme.px(16))
        self.scroll.setWidget(self.gallery)
        self.stack.addWidget(self.scroll)

        self.empty_state = TwoActionEmptyState(
            "library",
            tr("Your library is empty"),
            tr("Add local videos or download wallpapers from Discover"),
            tr("Add files"),
            tr("Explore Discover"),
        )
        self.stack.addWidget(self.empty_state)

        self.no_results = TwoActionEmptyState(
            "search",
            tr("No wallpapers found"),
            tr("Try a different search or filter."),
            tr("Clear filters"),
            tr("Add files"),
        )
        self.stack.addWidget(self.no_results)
        self.root.addWidget(self.stack, 1)

    # ----------------------------------------------------------------- signals
    def _connect(self) -> None:
        self.search.textChanged.connect(lambda _text: self._search_timer.start())
        self.sort_combo.currentIndexChanged.connect(lambda _index: self.refresh())
        self.chips.chip_clicked.connect(lambda _key: self.refresh())
        self.view_toggle.changed.connect(self._on_view_changed)
        self.add_button.clicked.connect(self.add_files)
        self.import_button.clicked.connect(lambda: self.ctx.navigate("import"))
        self.merge_button.clicked.connect(self._open_merge)
        self.empty_state.action_clicked.connect(self.add_files)
        self.empty_state.secondary_clicked.connect(lambda: self.ctx.navigate("discover"))
        self.no_results.action_clicked.connect(self._clear_filters)
        self.no_results.secondary_clicked.connect(self.add_files)

        self.ctx.library.changed.connect(self._schedule_refresh)
        self.ctx.downloads.changed.connect(self._schedule_refresh)
        self.ctx.assignments_changed.connect(self._schedule_refresh)

    def _on_view_changed(self, mode: str) -> None:
        if mode == self._view_mode:
            return
        self._view_mode = mode
        self.refresh(force=True)

    def _open_merge(self) -> None:
        from ui.dialogs.merge_video import MergeVideoDialog

        dialog = MergeVideoDialog(self.ctx, self)
        dialog.exec()
        self.refresh(force=True)

    def _schedule_refresh(self) -> None:
        # Coalesce bursts (download ticks emit ``changed`` every ~700 ms).
        if self._refresh_pending:
            return
        self._refresh_pending = True
        QTimer.singleShot(0, self._run_scheduled_refresh)

    def _run_scheduled_refresh(self) -> None:
        self._refresh_pending = False
        self.refresh()

    def _clear_filters(self) -> None:
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.chips.set_current("all")
        self.refresh(force=True)

    # ----------------------------------------------------------------- refresh
    def refresh(self, force: bool = False) -> None:
        """Re-query the real database and update the gallery."""
        try:
            search = self.search.text().strip()
            if self.sort_combo.currentIndex() < 0:
                sort = "added"
            else:
                sort = str(self.sort_combo.currentData() or "added")
            kind = self.chips.current()
            items = self.ctx.library.list_items(search=search, sort=sort, kind=kind)
        except Exception:  # noqa: BLE001 - a DB hiccup must not kill the page
            log.exception("library refresh failed")
            return

        signature = (
            self._view_mode,
            tuple((item.id, item.title, item.is_favorite, item_is_local(item),
                   item.file_path, item.width, item.height, item.duration,
                   item.format) for item in items),
        )
        if force or signature != self._signature:
            self._signature = signature
            self._rebuild(items)
        else:
            for card, item in zip(self._cards, items):
                card.set_item(item)

        if items:
            self.stack.setCurrentIndex(0)
        elif search or kind != "all":
            self.stack.setCurrentIndex(2)
        else:
            self.stack.setCurrentIndex(1)
        self.count_label.setText(_plural_wallpapers(len(items)) if items else "")

    def _rebuild(self, items: list[MediaItem]) -> None:
        bar = self.scroll.verticalScrollBar()
        scroll_value = bar.value()
        while self.flow.count():
            layout_item = self.flow.takeAt(0)
            widget = layout_item.widget() if layout_item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._cards = []
        self._items = list(items)
        for item in items:
            card: LibraryCard | CompactCard
            if self._view_mode == "compact":
                card = CompactCard()
            else:
                card = LibraryCard()
            card.set_item(item)
            card.install_requested.connect(
                lambda media_id, c=card: self._install_clicked(media_id, c))
            card.favorite_toggled.connect(self._toggle_favorite)
            card.menu_requested.connect(self._open_context_menu)
            card.clicked.connect(lambda media_id=item.id: self._preview(media_id))
            self.flow.addWidget(card)
            self._cards.append(card)
        self.gallery.updateGeometry()
        QTimer.singleShot(0, lambda: bar.setValue(min(scroll_value, bar.maximum())))
        log.debug("library gallery rebuilt: %d item(s), %s view", len(items), self._view_mode)

    # ----------------------------------------------------------------- actions
    def add_files(self) -> list[int]:
        start_dir = str(self.ctx.library.library_dir())
        paths, _selected_filter = QFileDialog.getOpenFileNames(
            self, tr("Add wallpapers to library"), start_dir, ADD_FILE_FILTER)
        if not paths:
            return []
        ids, errors = self.ctx.library.import_files(paths)
        summary = getattr(self.ctx.library, "last_import_summary", {}) or {}
        added = int(summary.get("added", len(ids)) or 0)
        existing = int(summary.get("existing", 0) or 0)
        if added:
            message = (tr("Added 1 file to the library") if added == 1
                       else tr("Added {count} files to the library", count=added))
            if existing:
                message = tr("{message} ({count} already in the library)",
                             message=message, count=existing)
            self.ctx.notify(message, "ok")
        elif existing:
            self.ctx.notify(tr("These files are already in the library"), "ok")
        if errors:
            details = "\n".join(errors[:8])
            if len(errors) > 8:
                details += tr("\n…and {count} more", count=len(errors) - 8)
            QMessageBox.warning(self, tr("Some files could not be added"), details)
        self.refresh(force=True)
        return ids

    def _install_clicked(self, media_id: int, card) -> None:
        item = self.ctx.library.get(int(media_id))
        if item is None:
            return
        if not item_is_local(item):
            self.ctx.notify(tr("The file is missing on disk"), "warn")
            return
        anchor = getattr(card, "install_button", None) or card
        position = anchor.mapToGlobal(QPoint(0, anchor.height() + 2))
        show_install_menu(self.ctx, int(media_id), position, self)

    def _toggle_favorite(self, media_id: int) -> None:
        try:
            value = self.ctx.library.toggle_favorite(int(media_id))
        except Exception:  # noqa: BLE001
            log.exception("could not toggle favorite for media %s", media_id)
            return
        self.ctx.notify(tr("Added to favorites") if value else tr("Removed from favorites"),
                        "ok")

    def _preview(self, media_id: int | None) -> None:
        if media_id is None:
            return
        item = self.ctx.library.get(int(media_id))
        if item is None:
            return
        open_media_preview(self.ctx, item, self)

    def _remove_item(self, item: MediaItem) -> None:
        if item.id is None:
            return
        accepted, delete_file = confirm_remove(self, item)
        if not accepted:
            return
        error = self.ctx.library.remove_record(int(item.id), delete_file=delete_file)
        if error:
            QMessageBox.warning(
                self, tr("Could not delete the file"),
                tr("The file could not be deleted, the library entry was kept:\n\n{error}",
                   error=error))
            return
        self.ctx.notify(tr("Removed from library"), "ok")
        self.refresh(force=True)

    # ------------------------------------------------------------- context menu
    def _show_details(self, item: MediaItem) -> None:
        lines = [f"{tr('Title')}: {item.title or tr('Untitled')}"]
        if item.author:
            lines.append(f"{tr('Author')}: {item.author}")
        if item.source:
            lines.append(f"{tr('Source')}: {item.source}")
        if item.imported_at:
            lines.append(f"{tr('Imported at')}: {item.imported_at}")
        if item.width and item.height:
            lines.append(f"{tr('Resolution')}: {item.resolution}")
        if item.aspect:
            lines.append(f"{tr('Aspect ratio')}: {item.aspect}")
        if item.duration:
            lines.append(f"{tr('Duration')}: {utils.human_duration(item.duration)}")
        if item.page_url:
            lines.append(f"{tr('Source page')}: {item.page_url}")
        if item.original_path:
            lines.append(f"{tr('Original file')}: {item.original_path}")
        if item.optimized_path:
            lines.append(f"{tr('Optimized copy')}: {item.optimized_path}")
        QMessageBox.information(self, tr("Import details"), "\n".join(lines))

    def _build_context_menu(self, item: MediaItem) -> QMenu:
        """Build the context menu; every action carries ``(kind, payload)`` data."""
        theme = current_theme()
        local = item_is_local(item)
        menu = QMenu(self)
        menu.setToolTipsVisible(True)

        primary = self.ctx.monitors.primary()
        install_text = (tr("Install on {name}", name=primary.name) if primary is not None
                        else tr("Install on primary monitor"))
        install_action = menu.addAction(
            icons.icon("play", theme.color("accent"), theme.px(16)), install_text)
        install_action.setEnabled(local)
        install_action.setData(("install_primary", None))

        monitor_menu = menu.addMenu(
            icons.icon("monitors", theme.color("text"), theme.px(16)),
            tr("Install on monitor"))
        monitor_menu.setEnabled(local)
        monitors = self.ctx.monitors.monitors()
        if not monitors:
            empty_action = monitor_menu.addAction(tr("No monitors detected"))
            empty_action.setEnabled(False)
        for monitor in monitors:
            label = tr("{name} ({resolution})", name=monitor.name,
                       resolution=monitor.resolution)
            if monitor.primary:
                label = tr("{name} ({resolution}) · Primary", name=monitor.name,
                           resolution=monitor.resolution)
            action = monitor_menu.addAction(
                icons.icon("monitors", theme.color("text"), theme.px(16)), label)
            action.setData(("install_monitor", monitor.key))

        all_action = menu.addAction(
            icons.icon("wall", theme.color("text"), theme.px(16)),
            tr("Install on all monitors"))
        all_action.setEnabled(local)
        all_action.setData(("install_all", None))

        mode_menu = menu.addMenu(
            icons.icon("image", theme.color("text"), theme.px(16)), tr("Display mode"))
        mode_menu.setEnabled(local)
        current_fit = str((item.meta or {}).get("fit") or
                          self.ctx.settings.get("playback.fit", "cover"))
        for key in FIT_MODE_ORDER:
            mode_action = mode_menu.addAction(tr(FIT_MODES[key]))
            mode_action.setCheckable(True)
            mode_action.setChecked(key == current_fit)
            mode_action.setData(("fit", key))

        if item.original_path and item.kind == "video":
            reprocess_action = menu.addAction(
                icons.icon("refresh", theme.color("text"), theme.px(16)),
                tr("Reprocess video"))
            reprocess_action.setData(("reprocess", None))
        details_action = menu.addAction(
            icons.icon("search", theme.color("text"), theme.px(16)),
            tr("Import details"))
        details_action.setData(("details", None))
        menu.addSeparator()

        favorite = tr("Remove from favorites") if item.is_favorite else tr("Add to favorites")
        favorite_action = menu.addAction(
            icons.icon("star-filled" if item.is_favorite else "star",
                       theme.color("accent") if item.is_favorite else theme.color("text"),
                       theme.px(16)),
            favorite)
        favorite_action.setData(("favorite", None))
        preview_action = menu.addAction(
            icons.icon("video", theme.color("text"), theme.px(16)), tr("Open preview"))
        preview_action.setData(("preview", None))
        reveal_action = menu.addAction(
            icons.icon("folder", theme.color("text"), theme.px(16)),
            tr("Show file in Explorer"))
        reveal_action.setEnabled(local)
        reveal_action.setData(("reveal", None))
        if item.page_url:
            source_action = menu.addAction(
                icons.icon("external", theme.color("text"), theme.px(16)),
                tr("Open source page"))
            source_action.setData(("source", None))

        menu.addSeparator()
        remove_action = menu.addAction(
            icons.icon("trash", theme.color("error"), theme.px(16)),
            tr("Remove from library…"))
        remove_action.setData(("remove", None))

        menu.triggered.connect(
            lambda action: self._handle_menu_action(int(item.id or 0), action))
        return menu

    def _handle_menu_action(self, media_id: int, action) -> None:
        if media_id <= 0:
            return
        item = self.ctx.library.get(media_id)
        if item is None:
            return
        data = action.data()
        if not isinstance(data, tuple) or len(data) != 2:
            return
        kind, payload = data
        if kind == "install_primary":
            self.ctx.install_media(media_id)
        elif kind == "install_monitor":
            self.ctx.install_media(media_id, payload)
        elif kind == "install_all":
            self.ctx.apply_to_all(media_id)
        elif kind == "fit":
            self.ctx.set_media_fit(media_id, str(payload))
        elif kind == "reprocess":
            self.ctx.reprocess_media(media_id)
        elif kind == "details":
            self._show_details(item)
        elif kind == "favorite":
            self._toggle_favorite(media_id)
        elif kind == "preview":
            self._preview(media_id)
        elif kind == "reveal":
            utils.reveal_in_explorer(item.file_path or "")
        elif kind == "source":
            utils.open_url(item.page_url or "")
        elif kind == "remove":
            self._remove_item(item)

    def _open_context_menu(self, media_id: int, global_pos: QPoint) -> None:
        item = self.ctx.library.get(int(media_id))
        if item is None:
            return
        menu = self._build_context_menu(item)
        menu.exec(global_pos)
        menu.deleteLater()

    # -------------------------------------------------------------------- hooks
    def on_show(self) -> None:
        self.refresh()
