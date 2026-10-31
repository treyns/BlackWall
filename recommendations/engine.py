"""Recommendation sections built from real provider results.

Each block is loaded with a live search request against the configured
providers ("Popular now", "New videos", "Recommended for you", "Editor's
choice").  Nothing here invents wallpapers: when a section cannot be loaded the
reason is reported to the UI instead of fake placeholders.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from config.constants import RECOMMENDATION_SECTIONS
from core.logger import get_logger

log = get_logger("recommendations")

SECTION_ORDER = [section_id for section_id, _title in RECOMMENDATION_SECTIONS]


class RecommendationEngine(QObject):
    """Loads the recommendation blocks shown on the Discover page."""

    section_ready = Signal(str, list)      # section_id, list[SearchResult]
    section_failed = Signal(str, str)      # section_id, message
    sections_changed = Signal()

    def __init__(self, search_manager, settings, db=None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.search = search_manager
        self.settings = settings
        self.db = db
        self._requests: dict[str, str] = {}      # section_id -> request_id
        self._request_map: dict[str, str] = {}   # request_id -> section_id
        self.search.results_ready.connect(self._on_results)
        self.search.error.connect(self._on_error)

    # ------------------------------------------------------------------ public
    def load_section(self, section_id: str) -> str | None:
        """Start loading one section; a previous request for it is cancelled."""
        previous = self._requests.pop(section_id, None)
        if previous:
            self._request_map.pop(previous, None)
            self.search.cancel(previous)
        if not self.search.available_providers():
            message = "No search provider is configured"
            log.warning("section %s not loaded: %s", section_id, message)
            self.section_failed.emit(section_id, message)
            return None
        request_id = self.search.section_async(section_id)
        self._requests[section_id] = request_id
        self._request_map[request_id] = section_id
        return request_id

    def load_all(self, section_ids: list[str] | tuple[str, ...] | None = None) -> None:
        for section_id in (section_ids or SECTION_ORDER):
            self.load_section(section_id)

    def cancel(self, section_id: str) -> None:
        request_id = self._requests.pop(section_id, None)
        if request_id:
            self._request_map.pop(request_id, None)
            self.search.cancel(request_id)

    def cancel_all(self) -> None:
        for section_id in list(self._requests):
            self.cancel(section_id)

    # ---------------------------------------------------------------- events
    def _on_results(self, request_id: str, results: list) -> None:
        section_id = self._request_map.pop(request_id, None)
        if not section_id:
            return
        if self._requests.get(section_id) != request_id:
            return  # stale answer for a cancelled/replaced request
        self._requests.pop(section_id, None)
        log.debug("section %s ready: %d results", section_id, len(results or []))
        self.section_ready.emit(section_id, list(results or []))

    def _on_error(self, request_id: str, message: str) -> None:
        section_id = self._request_map.pop(request_id, None)
        if not section_id:
            return
        if self._requests.get(section_id) != request_id:
            return
        self._requests.pop(section_id, None)
        log.warning("section %s failed: %s", section_id, message)
        self.section_failed.emit(section_id, message)
