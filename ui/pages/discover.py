"""Discover page: real online wallpaper search, filters and recommendations.

Every card comes from a live provider request (Pixabay / Pexels).  Nothing on
this page is mocked: missing API keys, empty results and provider errors are
shown honestly instead of fake content.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config.constants import (
    CATEGORIES,
    DURATION_FILTERS,
    RECOMMENDATION_SECTIONS,
    RESOLUTIONS,
    SORT_OPTIONS,
)
from core.i18n import tr
from core.logger import get_logger
from core.models import SearchResult
from search.base import SearchFilters
from ui import icons
from ui.components.cards import ResultCard
from ui.components.flow import CardGrid, FlowLayout
from ui.components.widgets import (
    EmptyState,
    SectionHeader,
    caption,
    text_label,
)
from ui.dialogs.preview import open_preview
from ui.pages.base import BasePage
from ui.theme import current_theme

log = get_logger("discover")

PER_PAGE = 24
FORMAT_OPTIONS = [("any", "Any format"), ("mp4", "MP4"), ("webm", "WebM")]

_CATEGORY_QUERY = {category_id: query for category_id, _label, query in CATEGORIES}
_CATEGORY_LABEL = {category_id: label for category_id, label, _query in CATEGORIES}

# Provider-side ordering; duration/resolution are sorted locally by the manager.
_ORDER_FOR_SORT = {
    "relevance": "relevance",
    "popular": "popular",
    "new": "new",
    "duration": "popular",
    "resolution": "popular",
}


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget() if item else None
        child_layout = item.layout() if item else None
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)


class CategoryChips(QWidget):
    """The 12 category chips; click again to clear the selection."""

    changed = Signal(str)  # category id, or "" when cleared

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self._flow = FlowLayout(self, margin=0, spacing=theme.px(8))
        self._buttons: dict[str, QPushButton] = {}
        self._active = ""
        for category_id, label, _query in CATEGORIES:
            button = QPushButton(tr(label))
            button.setObjectName("Chip")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, cid=category_id: self._on_click(cid))
            self._buttons[category_id] = button
            self._flow.addWidget(button)

    def _on_click(self, category_id: str) -> None:
        if self._active == category_id:
            self.clear(emit=True)
            return
        self._active = category_id
        for key, button in self._buttons.items():
            button.setChecked(key == category_id)
        self.changed.emit(category_id)

    def clear(self, emit: bool = False) -> None:
        self._active = ""
        for button in self._buttons.values():
            button.setChecked(False)
        if emit:
            self.changed.emit("")

    def set_current(self, category_id: str) -> None:
        """Select a chip without emitting ``changed`` (used to restore state)."""
        self._active = category_id if category_id in self._buttons else ""
        for key, button in self._buttons.items():
            button.blockSignals(True)
            button.setChecked(key == self._active)
            button.blockSignals(False)

    def current(self) -> str:
        return self._active


class FilterRow(QWidget):
    """Resolution / format / duration / source / sort filters."""

    changed = Signal()

    def __init__(self, providers, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self._flow = FlowLayout(self, margin=0, spacing=theme.px(10))
        self.resolution = self._combo(
            [(key, tr(label)) for key, label, _size in RESOLUTIONS],
            tr("Any resolution"))
        self.format = self._combo(
            [(key, tr(label)) for key, label in FORMAT_OPTIONS], tr("Any format"))
        self.duration = self._combo(
            [(key, tr(label)) for key, label, _span in DURATION_FILTERS],
            tr("Any duration"))
        source_items = [("", tr("All sources"))]
        for provider in providers:
            source_items.append((provider.name, provider.display_name or provider.name))
        self.source = self._combo(source_items, tr("All sources"))
        self.sort = self._combo(
            [(key, tr(label)) for key, label in SORT_OPTIONS], tr("Relevance"))
        self.reset_button = QPushButton(tr("Reset filters"))
        self.reset_button.setObjectName("LinkButton")
        self.reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_button.clicked.connect(self.reset)
        self._flow.addWidget(self.reset_button)

    def _combo(self, items: list[tuple[str, str]], tooltip: str) -> QComboBox:
        combo = QComboBox()
        combo.setToolTip(tooltip)
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for key, label in items:
            combo.addItem(label, key)
        combo.currentIndexChanged.connect(lambda _index: self.changed.emit())
        self._flow.addWidget(combo)
        return combo

    # ------------------------------------------------------------------ state
    def values(self) -> dict[str, str]:
        return {
            "resolution": str(self.resolution.currentData() or "any"),
            "format": str(self.format.currentData() or "any"),
            "duration": str(self.duration.currentData() or "any"),
            "source": str(self.source.currentData() or ""),
            "sort": str(self.sort.currentData() or "relevance"),
        }

    def filters(self) -> SearchFilters:
        values = self.values()
        return SearchFilters(
            resolution=values["resolution"],
            formats={values["format"]} if values["format"] != "any" else set(),
            duration=values["duration"],
            sources={values["source"]} if values["source"] else set(),
            sort=values["sort"],
        )

    def is_default(self) -> bool:
        values = self.values()
        return (values["resolution"] == "any" and values["format"] == "any"
                and values["duration"] == "any" and not values["source"]
                and values["sort"] == "relevance")

    def reset(self) -> None:
        for combo in (self.resolution, self.format, self.duration,
                      self.source, self.sort):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.changed.emit()

    def set_values(self, values: dict[str, str]) -> None:
        """Restore filter values without emitting ``changed``."""
        mapping = {
            "resolution": self.resolution,
            "format": self.format,
            "duration": self.duration,
            "source": self.source,
            "sort": self.sort,
        }
        for field, combo in mapping.items():
            value = values.get(field)
            if value is None:
                continue
            index = combo.findData(value)
            if index >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)


class DiscoverPage(BasePage):
    PAGE_KEY = "discover"
    TITLE = "Discover"
    SUBTITLE = "Find live wallpapers online"

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self._sections: dict[str, dict] = {}
        self._cards_by_uid: dict[str, list[ResultCard]] = {}
        self._search_cards: list[ResultCard] = []
        self._loaded_once = False
        self._mode = "browse"          # browse | search
        self._search_request = ""
        self._search_busy = False
        self._search_append = False
        self._search_query = ""
        self._search_category = ""
        self._search_filters = SearchFilters()
        self._search_page = 1
        self._search_results: list[SearchResult] = []
        self._seen_uids: set[str] = set()
        self._last_batch = 0
        self._provider_signature: tuple[str, ...] = ()
        self._recommendations_stale = True
        self._build_ui()
        self._connect()
        self._update_provider_state()
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._save_state)
        self._restore_pending = False
        self._restore_state()

    # ------------------------------------------------------------------- build
    def _build_ui(self) -> None:
        theme = self.theme

        # ------------------------------------------------- provider notices
        self.banner = QFrame()
        self.banner.setObjectName("Surface")
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(theme.px(14), theme.px(10),
                                         theme.px(14), theme.px(10))
        banner_layout.setSpacing(theme.px(10))
        banner_icon = QLabel()
        banner_icon.setPixmap(icons.pixmap("key", theme.color("warning"), theme.px(18)))
        banner_icon.setFixedSize(theme.px(18), theme.px(18))
        banner_layout.addWidget(banner_icon)
        self.banner_label = text_label("", "Body")
        self.banner_label.setWordWrap(True)
        banner_layout.addWidget(self.banner_label, 1)
        banner_settings = QPushButton(tr("Open settings"))
        banner_settings.setObjectName("Outline")
        banner_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        banner_settings.clicked.connect(lambda: self.ctx.navigate("settings"))
        banner_layout.addWidget(banner_settings)
        self.banner.setVisible(False)
        self.root.addWidget(self.banner)

        # ------------------------------------------------------ no providers
        self.no_provider_host = QWidget()
        no_provider_layout = QVBoxLayout(self.no_provider_host)
        no_provider_layout.setContentsMargins(0, 0, 0, 0)
        self._no_provider_layout = no_provider_layout
        self.no_provider_host.setVisible(False)
        self.root.addWidget(self.no_provider_host, 1)

        # --------------------------------------------------------- search bar
        self.search_row = QWidget()
        search_layout = QHBoxLayout(self.search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(theme.px(10))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            tr("Search live wallpapers, e.g. “cyberpunk city 4K”"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumHeight(theme.px(38))
        self.search_edit.returnPressed.connect(self._on_search_clicked)
        self.search_edit.textChanged.connect(self._on_query_changed)
        search_layout.addWidget(self.search_edit, 1)
        self.search_button = QPushButton(tr("Search"))
        self.search_button.setObjectName("Primary")
        self.search_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_button.setMinimumHeight(theme.px(38))
        self.search_button.setIcon(icons.icon("search", theme.color("accent_text"),
                                             theme.px(17)))
        self.search_button.clicked.connect(self._on_search_clicked)
        search_layout.addWidget(self.search_button)
        self.root.addWidget(self.search_row)

        # ------------------------------------------------------ category chips
        self.chips = CategoryChips()
        self.chips.changed.connect(self._on_category_selected)
        self.chips.hide()

        # ------------------------------------------------------------ filters
        self.filters = FilterRow(self.ctx.search.providers())
        self.filters.changed.connect(self._on_filters_changed)
        self.root.addWidget(self.filters)

        # ------------------------------------------------------------ content
        self.content_host = QWidget()
        self.content_layout = QVBoxLayout(self.content_host)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(theme.px(18))
        self.root.addWidget(self.content_host, 1)

        # browse: recommendation blocks
        self.browse_host = QWidget()
        self.browse_layout = QVBoxLayout(self.browse_host)
        self.browse_layout.setContentsMargins(0, 0, 0, 0)
        self.browse_layout.setSpacing(theme.px(26))
        for section_id, title in RECOMMENDATION_SECTIONS:
            self._build_section(section_id, title)
        self.content_layout.addWidget(self.browse_host)

        # search: results grid + load more
        self.search_host = QWidget()
        search_host_layout = QVBoxLayout(self.search_host)
        search_host_layout.setContentsMargins(0, 0, 0, 0)
        search_host_layout.setSpacing(theme.px(12))
        self.results_header = SectionHeader(tr("Results"), "")
        search_host_layout.addWidget(self.results_header)
        self.search_skeleton = self._make_skeleton_row()
        self.search_skeleton.setVisible(False)
        search_host_layout.addWidget(self.search_skeleton)
        self.results_grid = CardGrid(spacing=theme.px(16))
        search_host_layout.addWidget(self.results_grid)
        self.search_empty_host = QWidget()
        self.search_empty_layout = QVBoxLayout(self.search_empty_host)
        self.search_empty_layout.setContentsMargins(0, 0, 0, 0)
        search_host_layout.addWidget(self.search_empty_host)
        self.load_more_row = QWidget()
        load_more_layout = QHBoxLayout(self.load_more_row)
        load_more_layout.setContentsMargins(0, theme.px(4), 0, 0)
        load_more_layout.addStretch(1)
        self.load_more_button = QPushButton(tr("Load more"))
        self.load_more_button.setObjectName("Outline")
        self.load_more_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.load_more_button.clicked.connect(self._load_more)
        load_more_layout.addWidget(self.load_more_button)
        load_more_layout.addStretch(1)
        self.load_more_row.setVisible(False)
        search_host_layout.addWidget(self.load_more_row)
        self.search_host.setVisible(False)
        self.content_layout.addWidget(self.search_host)

    def _build_section(self, section_id: str, title: str) -> None:
        theme = self.theme
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.px(10))

        right = QWidget()
        right_layout = QHBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(theme.px(8))
        status = caption("")
        error = text_label("", "Error")
        error.setWordWrap(True)
        error.setVisible(False)
        retry = QPushButton(tr("Retry"))
        retry.setObjectName("LinkButton")
        retry.setCursor(Qt.CursorShape.PointingHandCursor)
        retry.setVisible(False)
        right_layout.addWidget(status)
        right_layout.addWidget(error)
        right_layout.addWidget(retry)

        header = SectionHeader(tr(title), "", right=right)
        layout.addWidget(header)

        skeleton = self._make_skeleton_row()
        skeleton.setVisible(False)
        layout.addWidget(skeleton)

        grid = CardGrid(spacing=theme.px(16))
        layout.addWidget(grid)

        block = {
            "widget": widget,
            "header": header,
            "status": status,
            "error": error,
            "retry": retry,
            "skeleton": skeleton,
            "grid": grid,
            "cards": [],
        }
        self._sections[section_id] = block
        self.browse_layout.addWidget(widget)
        status.setText(tr("Loading…"))
        retry.clicked.connect(
            lambda _checked=False, sid=section_id: self._load_section(sid))

    def _make_skeleton_row(self, count: int = 3) -> QWidget:
        theme = self.theme
        holder = QWidget()
        flow = FlowLayout(holder, margin=0, spacing=theme.px(16))
        for _index in range(count):
            card = QFrame()
            card.setObjectName("Card")
            card.setFixedSize(theme.px(ResultCard.CARD_WIDTH),
                              theme.px(286))
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(0, 0, 0, 0)
            card_layout.setSpacing(0)
            thumb = QFrame()
            thumb.setObjectName("Surface")
            thumb.setFixedHeight(theme.px(ResultCard.THUMB_HEIGHT))
            card_layout.addWidget(thumb)
            body = QVBoxLayout()
            body.setContentsMargins(theme.px(14), theme.px(12),
                                    theme.px(14), theme.px(12))
            body.addWidget(caption(tr("Loading…")))
            body.addStretch(1)
            card_layout.addLayout(body)
            flow.addWidget(card)
        return holder

    # --------------------------------------------------------------- signals
    def _connect(self) -> None:
        self.ctx.search.results_ready.connect(self._on_results_ready)
        self.ctx.search.error.connect(self._on_search_error)
        self.ctx.search.providers_changed.connect(self._on_providers_changed)
        self.ctx.recommendations.section_ready.connect(self._on_section_ready)
        self.ctx.recommendations.section_failed.connect(self._on_section_failed)
        self.ctx.library.changed.connect(self._on_library_changed)
        settings = self.ctx.settings
        listener = self._on_settings_changed
        settings.add_listener(listener)
        self.destroyed.connect(lambda *_args: settings.remove_listener(listener))

    # --------------------------------------------------------------- lifecycle
    def on_show(self) -> None:
        self._update_provider_state()
        if not self.ctx.search.available_providers():
            return
        if self._restore_pending:
            self._restore_pending = False
            query, category = self._combined_query()
            if query:
                self._start_search(query, category, page=1)
                return
        if not self._loaded_once or (self._recommendations_stale
                                     and self._mode == "browse"):
            self._load_recommendations()

    def on_hide(self) -> None:
        self._save_state()

    def refresh(self) -> None:
        self._update_provider_state()
        if not self.ctx.search.available_providers():
            return
        if self._mode == "browse":
            self._load_recommendations()
        elif self._search_query:
            self._start_search(self._search_query, self._search_category, page=1)

    # ------------------------------------------------------------- providers
    def _provider_label(self, name: str) -> str:
        for provider in self.ctx.search.providers():
            if provider.name == name:
                return provider.display_name or provider.name
        return name.upper()

    def _on_providers_changed(self) -> None:
        self._update_provider_state()

    def _on_settings_changed(self, key: str) -> None:
        if key and not key.startswith("providers."):
            return
        try:
            self.ctx.search.reload_providers()
        except Exception:  # noqa: BLE001 - a settings change must not crash the UI
            log.exception("could not reload providers")
        self._recommendations_stale = True
        self._update_provider_state()
        if self.isVisible() and self._mode == "browse" \
                and self.ctx.search.available_providers():
            self._load_recommendations()

    def _update_provider_state(self) -> None:
        providers = self.ctx.search.providers()
        available = [provider for provider in providers if provider.available()]
        missing = [provider.display_name or provider.name for provider in providers
                   if provider.enabled() and not provider.available()]
        enabled_any = any(provider.enabled() for provider in providers)
        has_provider = bool(available)

        for widget in (self.search_row, self.filters, self.content_host):
            widget.setVisible(has_provider)
        self.no_provider_host.setVisible(not has_provider)
        if not has_provider:
            self._show_no_provider_state(enabled_any)
            self.banner.setVisible(False)
            return

        self.banner.setVisible(bool(missing))
        if missing:
            available_names = ", ".join(
                provider.display_name or provider.name for provider in available)
            self.banner_label.setText(tr(
                "{missing} is enabled but has no API key - results come from "
                "{available} only. Add the key in Settings to include it.",
                missing=", ".join(missing), available=available_names))
        signature = tuple(sorted(provider.name for provider in available))
        if signature != self._provider_signature:
            self._provider_signature = signature
            self._recommendations_stale = True

    def _show_no_provider_state(self, enabled_any: bool) -> None:
        _clear_layout(self._no_provider_layout)
        if enabled_any:
            title = tr("No online source is ready")
            subtitle = tr("Add a free Pixabay API key or a Pexels API key in "
                          "Settings to search and download real live wallpapers.")
        else:
            title = tr("No online source is enabled")
            subtitle = tr("Enable Pixabay or Pexels in Settings and add their API "
                          "key to search real live wallpapers. The apps work fully "
                          "with local files too.")
        state = EmptyState("key", title, subtitle, tr("Open settings"))
        state.action_clicked.connect(lambda: self.ctx.navigate("settings"))
        self._no_provider_layout.addWidget(state)

    # ---------------------------------------------------- recommendations
    def _load_recommendations(self) -> None:
        if self._mode != "browse":
            self._recommendations_stale = True
            return
        if not self.ctx.search.available_providers():
            self._update_provider_state()
            return
        self._loaded_once = True
        self._recommendations_stale = False
        for section_id, _title in RECOMMENDATION_SECTIONS:
            self._load_section(section_id)

    def _load_section(self, section_id: str) -> None:
        block = self._sections.get(section_id)
        if block is None:
            return
        if self._mode != "browse":
            return
        self._forget_cards(block["cards"])
        block["cards"] = []
        block["grid"].clear()
        block["error"].setVisible(False)
        block["retry"].setVisible(False)
        block["status"].setText(tr("Loading…"))
        block["status"].setVisible(True)
        block["skeleton"].setVisible(True)
        self.ctx.recommendations.load_section(section_id)

    def _on_section_ready(self, section_id: str, results: list) -> None:
        block = self._sections.get(section_id)
        if block is None or self._mode != "browse":
            return
        block["skeleton"].setVisible(False)
        block["status"].setVisible(True)
        block["error"].setVisible(False)
        block["retry"].setVisible(False)
        self._forget_cards(block["cards"])
        block["cards"] = []
        block["grid"].clear()
        items: list[SearchResult] = [item for item in results
                                     if isinstance(item, SearchResult)]
        if not items:
            block["status"].setText(tr("No videos found for this section right now."))
            return
        providers = sorted({self._provider_label(item.provider) for item in items})
        block["status"].setText(tr("{count} videos · {providers}",
                                   count=len(items), providers=", ".join(providers)))
        for item in items:
            card = self._make_card(item)
            block["grid"].add_card(card)
            block["cards"].append(card)

    def _on_section_failed(self, section_id: str, message: str) -> None:
        block = self._sections.get(section_id)
        if block is None:
            return
        block["skeleton"].setVisible(False)
        block["status"].setVisible(False)
        block["error"].setText(tr("Could not load this section: {error}",
                                  error=message))
        block["error"].setVisible(True)
        block["retry"].setVisible(True)
        log.warning("recommendation section %s failed: %s", section_id, message)

    # ------------------------------------------------------------ cards
    def _make_card(self, result: SearchResult) -> ResultCard:
        card = ResultCard()
        card.set_result(result, favorite=self._is_favorite(result))
        parts = [part for part in (
            result.author or "",
            (result.format or "").upper(),
            result.duration_text if result.duration else "",
        ) if part]
        card.meta_label.setText(" · ".join(parts) or "—")
        tooltip = result.title or ""
        if result.tags:
            tooltip += "\n" + ", ".join(result.tags[:10])
        if tooltip:
            card.setToolTip(tooltip)
        card.preview_requested.connect(self._open_preview)
        card.download_requested.connect(self._download_result)
        card.favorite_requested.connect(self._toggle_favorite)
        card.clicked.connect(lambda item=result: self._open_preview(item))
        self._cards_by_uid.setdefault(result.uid, []).append(card)
        return card

    def _forget_cards(self, cards: list[ResultCard]) -> None:
        for card in cards:
            result = card.result
            uid = result.uid if result is not None else ""
            bucket = self._cards_by_uid.get(uid)
            if bucket and card in bucket:
                bucket.remove(card)
            if bucket is not None and not bucket:
                self._cards_by_uid.pop(uid, None)

    def _is_favorite(self, result: SearchResult) -> bool:
        try:
            stored = self.ctx.db.get_by_source(result.provider, result.source_id)
            return bool(stored and stored.is_favorite)
        except Exception:  # noqa: BLE001 - favourites must never break Discover
            log.exception("could not read favourite state")
            return False

    def _apply_favorite_state(self, uid: str, value: bool) -> None:
        for card in self._cards_by_uid.get(uid, []):
            card.set_favorite(value)

    def _refresh_favorite_icons(self, uid: str | None = None) -> None:
        uids = [uid] if uid else list(self._cards_by_uid)
        for key in uids:
            cards = self._cards_by_uid.get(key) or []
            if not cards or cards[0].result is None:
                continue
            value = self._is_favorite(cards[0].result)
            for card in cards:
                card.set_favorite(value)

    def _on_library_changed(self) -> None:
        self._refresh_favorite_icons()

    # ----------------------------------------------------------- card actions
    def _open_preview(self, result: SearchResult) -> None:
        try:
            open_preview(self.ctx, result, self)
        except Exception:  # noqa: BLE001 - a broken preview must not kill the page
            log.exception("preview dialog failed")
            self.ctx.notify(tr("Could not open the preview"), "error")
        self._refresh_favorite_icons(result.uid)

    def _download_result(self, result: SearchResult) -> None:
        try:
            self.ctx.downloads.start_download(result)
        except Exception as error:  # noqa: BLE001
            log.warning("could not start download for %s: %s", result.uid, error)
            self.ctx.notify(tr("Could not start the download: {error}",
                               error=str(error)), "error")
            return
        self.ctx.notify(tr("Download started: {title}",
                           title=result.title or result.source_id), "ok")
        self._refresh_favorite_icons(result.uid)

    def _toggle_favorite(self, result: SearchResult) -> None:
        try:
            stored = self.ctx.db.get_by_source(result.provider, result.source_id)
            if stored is None:
                self.ctx.library.add_from_search(result, favorite=True)
                value = True
            else:
                value = not stored.is_favorite
                if stored.id is not None:
                    self.ctx.library.set_favorite(int(stored.id), value)
        except Exception as error:  # noqa: BLE001
            log.warning("favourite toggle failed for %s: %s", result.uid, error)
            self.ctx.notify(tr("Could not update favorites: {error}",
                               error=str(error)), "error")
            return
        self._apply_favorite_state(result.uid, value)
        self.ctx.notify(tr("Added to favorites") if value
                        else tr("Removed from favorites"), "ok")

    # --------------------------------------------------------------- searching
    def _combined_query(self) -> tuple[str, str]:
        """Effective query = search text + selected category (both may be set)."""
        text = self.search_edit.text().strip()
        category = self.chips.current()
        parts: list[str] = []
        if text:
            parts.append(text)
        if category:
            category_query = _CATEGORY_QUERY.get(category, "")
            if category_query:
                parts.append(category_query)
        return " ".join(parts).strip(), category

    def _save_state(self) -> None:
        try:
            self.ctx.settings.set("discover.state", {
                "query": self.search_edit.text(),
                "category": self.chips.current(),
                "filters": self.filters.values(),
                "mode": self._mode,
            })
        except Exception:  # noqa: BLE001 - persistence must never break search
            log.exception("could not save discover state")

    def _restore_state(self) -> None:
        state = self.ctx.settings.get("discover.state", {}) or {}
        if not isinstance(state, dict):
            return
        query = str(state.get("query") or "")
        category = str(state.get("category") or "")
        self.search_edit.blockSignals(True)
        self.search_edit.setText(query)
        self.search_edit.blockSignals(False)
        self.chips.clear()
        filters = state.get("filters")
        if isinstance(filters, dict):
            self.filters.set_values(filters)
        effective, _category = self._combined_query()
        if effective:
            self._restore_pending = True

    def _on_query_changed(self, text: str) -> None:
        if self._save_timer is not None:
            self._save_timer.start()
        if not text.strip() and self._mode == "search" and not self.chips.current():
            self._show_browse()

    def _on_search_clicked(self) -> None:
        query, category = self._combined_query()
        if not query:
            self._show_browse()
            return
        self._start_search(query, category, page=1)
        self._save_state()

    def _on_category_selected(self, category_id: str) -> None:
        # The category is an additional condition: the search text stays intact.
        query, category = self._combined_query()
        if not query:
            self._show_browse()
        else:
            self._start_search(query, category, page=1)
        self._save_state()

    def _on_filters_changed(self) -> None:
        self._save_timer.start() if self._save_timer is not None else None
        query, category = self._combined_query()
        if self._mode == "search" and query:
            self._start_search(query, category, page=1)
        elif self._mode == "search" and not query:
            self._show_browse()

    def _reset_filters(self) -> None:
        """Reset only the filter row; the search query is kept."""
        self.filters.reset()
        self._save_state()

    def _active_sources(self, filters: SearchFilters) -> list:
        available = self.ctx.search.available_providers()
        if filters.sources:
            available = [provider for provider in available
                         if provider.name in filters.sources]
        return available

    def _start_search(self, query: str, category: str, page: int = 1,
                      append: bool = False) -> None:
        filters = self.filters.filters() if not append else self._search_filters
        active = self._active_sources(filters)
        if not active:
            self._show_missing_source(filters)
            return
        if not append:
            self._search_query = query
            self._search_category = category
            self._search_filters = filters
        if self._search_request:
            self.ctx.search.cancel(self._search_request)
            self._search_request = ""
        self._search_append = append
        self._search_page = page
        self._mode = "search"
        self.browse_host.setVisible(False)
        self.search_host.setVisible(True)
        if not append:
            self._search_page = page
            self._search_results = []
            self._seen_uids = set()
            self._last_batch = 0
            self._clear_search_grid()
            self._clear_search_state()
        self._set_search_busy(True, first_page=not append)
        self._update_results_header(busy=True, active=active)
        self.scroll_to_top()
        request_id = self.ctx.search.search_async(
            query, filters, page=page, per_page=PER_PAGE,
            order=_ORDER_FOR_SORT.get(filters.sort, "popular"))
        self._search_request = request_id
        log.info("discover search %r page %s filters=%s", query, page, filters)

    def _on_results_ready(self, request_id: str, results: list) -> None:
        if not self._search_request or request_id != self._search_request:
            return
        self._search_request = ""
        items: list[SearchResult] = [item for item in results
                                     if isinstance(item, SearchResult)]
        self._last_batch = len(items)
        if self._search_append:
            new_items = [item for item in items if item.uid not in self._seen_uids]
            for item in new_items:
                self._seen_uids.add(item.uid)
                self._search_results.append(item)
                card = self._make_card(item)
                self.results_grid.add_card(card)
                self._search_cards.append(card)
        else:
            self._search_results = []
            self._seen_uids = set()
            for item in items:
                self._seen_uids.add(item.uid)
                self._search_results.append(item)
                card = self._make_card(item)
                self.results_grid.add_card(card)
                self._search_cards.append(card)
        self._set_search_busy(False, first_page=not self._search_append)
        self._update_results_header(busy=False)
        if not self._search_results:
            self._show_no_results_state()
        else:
            self._clear_search_state()
        self._load_more_row_visible()
        log.info("discover search finished: %d total results", len(self._search_results))

    def _on_search_error(self, request_id: str, message: str) -> None:
        if not self._search_request or request_id != self._search_request:
            return
        self._search_request = ""
        self._set_search_busy(False, first_page=not self._search_append)
        self._clear_search_state()
        if self._search_append and self._search_results:
            # Keep the already loaded pages; only the extra page failed.
            self._last_batch = 0
            self.load_more_row.setVisible(False)
            self._set_search_state(
                "refresh", tr("Could not load more results"),
                tr("{error}. Try again in a moment.", error=message),
                tr("Try again"), self._load_more)
            log.warning("discover load-more failed: %s", message)
            return
        self._last_batch = 0
        self._clear_search_grid()
        self._search_results = []
        self._seen_uids = set()
        self._load_more_row_visible()
        self.results_header.set_title(tr("Results"))
        self.results_header.set_subtitle(tr("Provider error"))
        lower = message.lower()
        key_problem = any(marker in lower for marker in
                          ("key", "rejected", "forbidden", "authoriz"))
        if key_problem:
            self._set_search_state(
                "key", tr("Search failed"),
                tr("{error}. Check the provider API key in Settings.",
                   error=message),
                tr("Open settings"),
                lambda: self.ctx.navigate("settings"))
        else:
            self._set_search_state(
                "refresh", tr("Search failed"),
                tr("{error}. Check your internet connection and try again.",
                   error=message),
                tr("Try again"),
                self._retry_search)
        log.warning("discover search failed: %s", message)

    def _retry_search(self) -> None:
        if self._search_query:
            self._start_search(self._search_query, self._search_category, page=1)

    def _load_more(self) -> None:
        if self._search_busy or not self._search_query:
            return
        self._start_search(self._search_query, self._search_category,
                           page=self._search_page + 1, append=True)

    # ---------------------------------------------------------- search states
    def _set_search_busy(self, busy: bool, first_page: bool = False) -> None:
        self._search_busy = busy
        if busy:
            if first_page:
                self.search_skeleton.setVisible(True)
                self.load_more_row.setVisible(False)
            self.load_more_button.setEnabled(False)
            self.load_more_button.setText(tr("Loading…"))
        else:
            self.search_skeleton.setVisible(False)
            self.load_more_button.setEnabled(True)
            self.load_more_button.setText(tr("Load more"))

    def _update_results_header(self, busy: bool, active: list | None = None) -> None:
        if self._search_query:
            self.results_header.set_title(
                tr("Results for “{query}”", query=self._search_query))
        else:
            self.results_header.set_title(tr("Results"))
        if busy:
            providers = ", ".join(
                provider.display_name or provider.name
                for provider in (active or self.ctx.search.available_providers()))
            self.results_header.set_subtitle(
                tr("Searching {providers}…", providers=providers or tr("online sources")))
            return
        parts: list[str] = []
        if self._search_category:
            label = _CATEGORY_LABEL.get(self._search_category, self._search_category)
            parts.append(tr("Category: {name}", name=tr(label)))
        if self._search_results:
            providers = sorted({self._provider_label(item.provider)
                                for item in self._search_results})
            parts.append(tr("{count} videos loaded", count=len(self._search_results)))
            if providers:
                parts.append(", ".join(providers))
        self.results_header.set_subtitle(" · ".join(parts)
                                         or tr("No provider returned results"))

    def _load_more_row_visible(self) -> None:
        can_load_more = (not self._search_busy
                         and self._last_batch >= PER_PAGE)
        self.load_more_row.setVisible(can_load_more)

    def _clear_search_grid(self) -> None:
        self._forget_cards(self._search_cards)
        self._search_cards = []
        self.results_grid.clear()

    def _clear_search_state(self) -> None:
        _clear_layout(self.search_empty_layout)

    def _set_search_state(self, icon_name: str, title: str, subtitle: str,
                          action_text: str, callback) -> None:
        _clear_layout(self.search_empty_layout)
        state = EmptyState(icon_name, title, subtitle, action_text)
        state.action_clicked.connect(callback)
        self.search_empty_layout.addWidget(state)
        self.search_empty_layout.addStretch(1)

    def _show_no_results_state(self) -> None:
        if not self.filters.is_default():
            self._set_search_state(
                "discover", tr("No results found"),
                tr("Nothing matched this query with the selected filters. "
                   "Try different keywords or reset the filters."),
                tr("Reset filters"), self._reset_filters)
        else:
            self._set_search_state(
                "discover", tr("No results found"),
                tr("Nothing matched “{query}”. Try different keywords, "
                   "another category or another source.", query=self._search_query),
                tr("Back to recommendations"), self._show_browse)

    def _show_missing_source(self, filters: SearchFilters) -> None:
        self._mode = "search"
        self.browse_host.setVisible(False)
        self.search_host.setVisible(True)
        self._clear_search_grid()
        self._clear_search_state()
        self._set_search_busy(False, first_page=True)
        self.load_more_row.setVisible(False)
        self.results_header.set_title(tr("Results"))
        providers = self.ctx.search.providers()
        missing = [provider.display_name or provider.name for provider in providers
                   if provider.enabled() and not provider.available()
                   and (not filters.sources or provider.name in filters.sources)]
        if missing:
            self.results_header.set_subtitle(tr("Provider not configured"))
            self._set_search_state(
                "key", tr("API key required"),
                tr("{providers} is enabled but no API key is set. Open Settings "
                   "to add the key, then search again.", providers=", ".join(missing)),
                tr("Open settings"), lambda: self.ctx.navigate("settings"))
        else:
            self.results_header.set_subtitle(tr("No sources selected"))
            self._set_search_state(
                "key", tr("No source selected"),
                tr("The selected source is disabled. Enable it in Settings or "
                   "choose another source."),
                tr("Open settings"), lambda: self.ctx.navigate("settings"))
        self.scroll_to_top()

    def _show_browse(self) -> None:
        if self._search_request:
            self.ctx.search.cancel(self._search_request)
            self._search_request = ""
        self._search_busy = False
        self._search_append = False
        self._mode = "browse"
        self.search_host.setVisible(False)
        self.browse_host.setVisible(True)
        self._search_query = ""
        self._search_category = ""
        if self._recommendations_stale and self.ctx.search.available_providers():
            self._load_recommendations()

