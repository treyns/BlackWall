"""Favorites page: liked wallpapers (local files and remote, not downloaded items)."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QWidget,
)

from core import utils
from core.i18n import tr
from core.logger import get_logger
from core.models import MediaItem
from library.ui_helpers import (
    FavoriteCard,
    TwoActionEmptyState,
    confirm_remove,
    item_is_local,
    open_media_preview,
    show_install_menu,
)
from ui import icons
from ui.components.flow import FlowLayout
from ui.components.widgets import dim
from ui.pages.base import BasePage
from ui.theme import current_theme

log = get_logger("page.favorites")

SORT_OPTIONS: list[tuple[str, str]] = [
    ("added", "Recently added"),
    ("title", "Title"),
    ("resolution", "Resolution"),
    ("duration", "Duration"),
]


def _plural_favorites(count: int) -> str:
    if count == 1:
        return tr("1 favorite")
    return tr("{count} favorites", count=count)


class FavoritesPage(BasePage):
    PAGE_KEY = "favorites"
    TITLE = "Favorites"
    SUBTITLE = "Wallpapers you liked"

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self._signature: tuple | None = None
        self._cards: list[FavoriteCard] = []
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

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(theme.px(10))

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search favorites"))
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
        self.sort_combo.setToolTip(tr("Sort favorites"))
        toolbar_layout.addWidget(self.sort_combo)

        self.count_label = dim("")
        toolbar_layout.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.root.addWidget(toolbar)

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
            "star",
            tr("No favorites yet"),
            tr("Find wallpapers you like in Discover"),
            tr("Explore Discover"),
        )
        self.stack.addWidget(self.empty_state)

        self.no_results = TwoActionEmptyState(
            "search",
            tr("No favorites found"),
            tr("Try a different search."),
            tr("Clear search"),
        )
        self.stack.addWidget(self.no_results)
        self.root.addWidget(self.stack, 1)

    # ----------------------------------------------------------------- signals
    def _connect(self) -> None:
        self.search.textChanged.connect(lambda _text: self._search_timer.start())
        self.sort_combo.currentIndexChanged.connect(lambda _index: self.refresh())
        self.empty_state.action_clicked.connect(lambda: self.ctx.navigate("discover"))
        self.no_results.action_clicked.connect(self._clear_search)
        self.ctx.library.changed.connect(self._schedule_refresh)

    def _schedule_refresh(self) -> None:
        if self._refresh_pending:
            return
        self._refresh_pending = True
        QTimer.singleShot(0, self._run_scheduled_refresh)

    def _run_scheduled_refresh(self) -> None:
        self._refresh_pending = False
        self.refresh()

    def _clear_search(self) -> None:
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.refresh(force=True)

    # ----------------------------------------------------------------- refresh
    def refresh(self, force: bool = False) -> None:
        try:
            search = self.search.text().strip()
            if self.sort_combo.currentIndex() < 0:
                sort = "added"
            else:
                sort = str(self.sort_combo.currentData() or "added")
            items = self.ctx.library.favorites(search=search, sort=sort)
        except Exception:  # noqa: BLE001
            log.exception("favorites refresh failed")
            return

        signature = (
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
        elif search:
            self.stack.setCurrentIndex(2)
        else:
            self.stack.setCurrentIndex(1)
        self.count_label.setText(_plural_favorites(len(items)) if items else "")

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
            card = FavoriteCard()
            card.set_item(item)
            card.install_requested.connect(
                lambda media_id, c=card: self._install_clicked(media_id, c))
            card.favorite_toggled.connect(self._remove_favorite)
            card.open_source_requested.connect(self._open_source)
            card.menu_requested.connect(self._open_context_menu)
            card.clicked.connect(lambda media_id=item.id: self._preview(media_id))
            self.flow.addWidget(card)
            self._cards.append(card)
        self.gallery.updateGeometry()
        QTimer.singleShot(0, lambda: bar.setValue(min(scroll_value, bar.maximum())))
        log.debug("favorites gallery rebuilt: %d item(s)", len(items))

    # ----------------------------------------------------------------- actions
    def _install_clicked(self, media_id: int, card) -> None:
        item = self.ctx.library.get(int(media_id))
        if item is None:
            return
        if not item_is_local(item):
            self.ctx.notify(tr("This wallpaper is not downloaded yet"), "warn")
            self._open_source(int(media_id))
            return
        anchor = getattr(card, "install_button", None) or card
        position = anchor.mapToGlobal(QPoint(0, anchor.height() + 2))
        show_install_menu(self.ctx, int(media_id), position, self)

    def _remove_favorite(self, media_id: int) -> None:
        try:
            self.ctx.library.set_favorite(int(media_id), False)
        except Exception:  # noqa: BLE001
            log.exception("could not remove favorite %s", media_id)
            return
        self.ctx.notify(tr("Removed from favorites"), "ok")
        self.refresh(force=True)

    def _open_source(self, media_id: int) -> None:
        item = self.ctx.library.get(int(media_id))
        if item is not None and item.page_url:
            utils.open_url(item.page_url)
        else:
            self.ctx.notify(tr("This wallpaper has no source link"), "warn")

    def _preview(self, media_id: int | None) -> None:
        if media_id is None:
            return
        item = self.ctx.library.get(int(media_id))
        if item is None:
            return
        open_media_preview(self.ctx, item, self)

    def _remove_record(self, item: MediaItem) -> None:
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
    def _build_context_menu(self, item: MediaItem) -> QMenu:
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
        menu.addSeparator()

        if not local:
            hint = menu.addAction(tr("Not downloaded yet — open the source to download it"))
            hint.setEnabled(False)
        remove_favorite_action = menu.addAction(
            icons.icon("star-filled", theme.color("accent"), theme.px(16)),
            tr("Remove from favorites"))
        remove_favorite_action.setData(("unfavorite", None))
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

        if local:
            menu.addSeparator()
            remove_record_action = menu.addAction(
                icons.icon("trash", theme.color("error"), theme.px(16)),
                tr("Remove from library…"))
            remove_record_action.setData(("remove", None))

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
        elif kind == "unfavorite":
            self._remove_favorite(media_id)
        elif kind == "preview":
            self._preview(media_id)
        elif kind == "reveal":
            utils.reveal_in_explorer(item.file_path or "")
        elif kind == "source":
            utils.open_url(item.page_url or "")
        elif kind == "remove":
            self._remove_record(item)

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
