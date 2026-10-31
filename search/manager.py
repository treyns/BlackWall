"""Search aggregator: queries all enabled providers in background threads."""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal

from config import paths
from config.constants import DURATION_FILTERS, RESOLUTION_MIN, SORT_OPTIONS
from core.logger import get_logger
from core.models import SearchResult
from search.base import ProviderBase, SearchFilters

log = get_logger("search")


class _RequestSignals(QObject):
    finished = Signal(str, list, list)  # request_id, results, errors


class _SearchWorker(QRunnable):
    def __init__(self, request_id: str, manager: "SearchManager", query: str,
                 filters: SearchFilters, page: int, per_page: int, order: str,
                 source: str = "search") -> None:
        super().__init__()
        self.request_id = request_id
        self.manager = manager
        self.query = query
        self.filters = filters
        self.page = page
        self.per_page = per_page
        self.order = order
        self.source = source
        self.signals = _RequestSignals()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def run(self) -> None:  # noqa: D401 - QRunnable API
        results: list[SearchResult] = []
        errors: list[str] = []
        started = time.time()
        providers = self.manager.active_providers(self.filters.sources)
        log.debug("request %s: query=%r page=%s providers=%s", self.request_id[:8],
                  self.query, self.page, [provider.name for provider in providers])
        for provider in providers:
            if self._cancelled.is_set():
                log.debug("request %s cancelled before %s", self.request_id[:8],
                          provider.name)
                return
            provider_started = time.time()
            try:
                cached = self.manager.cache_lookup(provider.name, self.query, self.page,
                                                   self.order, self.per_page)
                if cached is not None:
                    results.extend(cached)
                    log.debug("request %s: %s cache hit (%d items, %.2fs)",
                              self.request_id[:8], provider.name, len(cached),
                              time.time() - provider_started)
                    continue
                found = provider.search(self.query, page=self.page,
                                        per_page=self.per_page, order=self.order)
                if found:
                    self.manager.cache_store(provider.name, self.query, self.page,
                                             self.order, self.per_page, found)
                results.extend(found)
                log.debug("request %s: %s network -> %d items in %.2fs",
                          self.request_id[:8], provider.name, len(found),
                          time.time() - provider_started)
            except Exception as error:  # noqa: BLE001
                log.warning("request %s: provider %s failed: %s", self.request_id[:8],
                            provider.name, error)
                errors.append(f"{provider.display_name or provider.name}: {error}")
        if self._cancelled.is_set():
            log.debug("request %s cancelled", self.request_id[:8])
            return
        results = self.manager.apply_filters(results, self.filters)
        log.debug("request %s finished: %d results in %.2fs", self.request_id[:8],
                  len(results), time.time() - started)
        self.signals.finished.emit(self.request_id, results, errors)


class SearchManager(QObject):
    results_ready = Signal(str, list)   # request_id, list[SearchResult]
    error = Signal(str, str)            # request_id, message
    providers_changed = Signal()

    def __init__(self, settings, db=None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.db = db
        self._providers: dict[str, ProviderBase] = {}
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(4)
        self._workers: dict[str, _SearchWorker] = {}
        self._lock = threading.RLock()
        self._cache_dir = paths.SEARCH_CACHE_DIR
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.reload_providers()

    # --------------------------------------------------------------- providers
    def reload_providers(self) -> None:
        with self._lock:
            for provider in self._providers.values():
                provider.close()
            self._providers.clear()
            try:
                from search.providers import PROVIDER_CLASSES
            except ImportError:
                log.exception("search provider package is not importable")
                return
            for cls in PROVIDER_CLASSES:
                try:
                    provider = cls(self.settings)
                    self._providers[provider.name] = provider
                except Exception:  # noqa: BLE001
                    log.exception("could not load provider %s", cls)
        self.providers_changed.emit()

    def providers(self) -> list[ProviderBase]:
        return list(self._providers.values())

    def provider(self, name: str) -> ProviderBase | None:
        return self._providers.get(name)

    def available_providers(self) -> list[ProviderBase]:
        return [p for p in self._providers.values() if p.available()]

    def missing_key_providers(self) -> list[str]:
        return [p.display_name or p.name for p in self._providers.values()
                if p.enabled() and not p.available()]

    def active_providers(self, sources: set[str] | None = None) -> list[ProviderBase]:
        providers = [p for p in self._providers.values() if p.available()]
        if sources:
            providers = [p for p in providers if p.name in sources]
        return providers

    # -------------------------------------------------------------------- API
    def search_async(self, query: str, filters: SearchFilters | None = None,
                     page: int = 1, per_page: int = 24,
                     order: str = "popular") -> str:
        filters = filters or SearchFilters()
        request_id = uuid.uuid4().hex
        worker = _SearchWorker(request_id, self, query, filters, page, per_page, order)
        worker.signals.finished.connect(self._on_finished, Qt.ConnectionType.QueuedConnection)
        with self._lock:
            self._workers[request_id] = worker
        self._pool.start(worker)
        return request_id

    def section_async(self, section: str) -> str:
        """Load one of the recommendation sections."""
        from config.constants import CATEGORY_QUERY, CURATED_QUERIES

        request_id = uuid.uuid4().hex
        filters = SearchFilters()
        if section == "popular":
            query, order = CATEGORY_QUERY.get("cities", "city night"), "popular"
        elif section == "new":
            query, order = CATEGORY_QUERY.get("abstract", "abstract background"), "new"
        elif section == "curated":
            index = int(time.time() // 600) % max(1, len(CURATED_QUERIES))
            query, order = CURATED_QUERIES[index], "popular"
        else:  # recommended -> based on favourites, fallback to category mix
            query, order = self._recommended_query(), "popular"
        worker = _SearchWorker(request_id, self, query, filters, 1, 18, order, section)
        worker.signals.finished.connect(self._on_finished, Qt.ConnectionType.QueuedConnection)
        with self._lock:
            self._workers[request_id] = worker
        self._pool.start(worker)
        return request_id

    def cancel(self, request_id: str) -> None:
        with self._lock:
            worker = self._workers.pop(request_id, None)
        if worker is not None:
            worker.cancel()

    # ---------------------------------------------------------------- filters
    def apply_filters(self, results: list[SearchResult],
                      filters: SearchFilters) -> list[SearchResult]:
        filtered = list(results)
        if filters.sources:
            filtered = [r for r in filtered if r.provider in filters.sources]
        if filters.formats:
            filtered = [r for r in filtered
                        if (r.format or "mp4").lower() in {f.lower() for f in filters.formats}]
        min_size = RESOLUTION_MIN.get(filters.resolution)
        if min_size:
            filtered = [r for r in filtered
                        if r.width >= min_size[0] and r.height >= min_size[1]]
        duration_range = dict((key, span) for key, _label, span in DURATION_FILTERS).get(
            filters.duration, (0, 10 ** 9))
        filtered = [r for r in filtered
                    if duration_range[0] <= float(r.duration or 0) <= duration_range[1]]
        if filters.sort == "duration":
            filtered.sort(key=lambda r: float(r.duration or 0), reverse=True)
        elif filters.sort == "resolution":
            filtered.sort(key=lambda r: (r.width or 0) * (r.height or 0), reverse=True)
        # popularity / newest / relevance order is provider-side; keep it stable.
        seen: set[str] = set()
        unique: list[SearchResult] = []
        for result in filtered:
            if result.uid in seen:
                continue
            seen.add(result.uid)
            unique.append(result)
        return unique

    def _recommended_query(self) -> str:
        try:
            if self.db is not None:
                favorites = self.db.list_favorites()
                tags: list[str] = []
                for item in favorites[:6]:
                    tags.extend([str(t) for t in (item.meta.get("tags") or [])][:2])
                if tags:
                    return " ".join(tags[:3])
                recent = self.db.recent(4)
                for item in recent:
                    tags.extend([str(t) for t in (item.meta.get("tags") or [])][:2])
                if tags:
                    return " ".join(tags[:3])
        except Exception:  # noqa: BLE001
            pass
        return "nature landscape 4k"

    # ------------------------------------------------------------------ cache
    def _cache_file(self, provider: str, query: str, page: int, order: str,
                    per_page: int) -> Path:
        import hashlib

        key = f"{provider}|{query.lower().strip()}|{page}|{order}|{per_page}"
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.json"

    def cache_lookup(self, provider: str, query: str, page: int, order: str,
                     per_page: int) -> list[SearchResult] | None:
        ttl = int(self.settings.get("providers.search_cache_minutes", 30) or 30) * 60
        file = self._cache_file(provider, query, page, order, per_page)
        try:
            if not file.exists() or time.time() - file.stat().st_mtime > ttl:
                return None
            data = json.loads(file.read_text(encoding="utf-8"))
            return [SearchResult.from_dict(entry) for entry in data]
        except (OSError, ValueError):
            return None

    def cache_store(self, provider: str, query: str, page: int, order: str,
                    per_page: int, results: list[SearchResult]) -> None:
        file = self._cache_file(provider, query, page, order, per_page)
        try:
            file.write_text(json.dumps([r.to_dict() for r in results], ensure_ascii=False),
                            encoding="utf-8")
        except OSError:
            pass

    # ---------------------------------------------------------------- events
    def _on_finished(self, request_id: str, results: list, errors: list) -> None:
        with self._lock:
            self._workers.pop(request_id, None)
        if errors:
            if results:
                # Keep partial results but make the degradation visible in the log.
                log.warning("partial search results (%d), provider errors: %s",
                            len(results), "; ".join(errors))
            else:
                self.error.emit(request_id, "; ".join(errors))
                return
        self.results_ready.emit(request_id, results)
