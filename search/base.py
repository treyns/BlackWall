"""Provider interface: every wallpaper source is a separate module."""
from __future__ import annotations

from dataclasses import dataclass, field

import requests

from core.models import SearchResult


@dataclass
class SearchFilters:
    resolution: str = "any"          # key from config.constants.RESOLUTIONS
    formats: set[str] = field(default_factory=set)     # {"mp4", "webm"} / empty = all
    duration: str = "any"             # key from config.constants.DURATION_FILTERS
    categories: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)     # provider names / empty = all
    sort: str = "relevance"           # relevance/popular/new/duration/resolution


class ProviderBase:
    """Base class for search providers.

    Network calls are blocking; the search manager always calls them from a
    worker thread. Implementations must raise nothing but requests exceptions -
    the manager converts those into user-visible errors.
    """

    name: str = ""
    display_name: str = ""
    site: str = ""

    def __init__(self, settings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BlackWall/1.0 (live wallpaper app)",
            "Accept": "application/json",
        })

    # ------------------------------------------------------------------ status
    def api_key(self) -> str:
        return str(self.settings.get(f"providers.{self.name}_key", "") or "").strip()

    def enabled(self) -> bool:
        return bool(self.settings.get(f"providers.{self.name}_enabled", True))

    def available(self) -> bool:
        return self.enabled() and bool(self.api_key())

    def unavailable_reason(self) -> str:
        if not self.enabled():
            return "Disabled in settings"
        if not self.api_key():
            return "API key is not set"
        return ""

    # ------------------------------------------------------------------- calls
    def search(self, query: str, page: int = 1, per_page: int = 20,
               order: str = "popular") -> list[SearchResult]:
        raise NotImplementedError

    def fetch_meta(self, source_id: str) -> SearchResult | None:
        """Optional: refresh metadata for a single item."""
        return None

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:  # noqa: BLE001
            pass
