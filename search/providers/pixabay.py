"""Pixabay video provider (official API: https://pixabay.com/api/docs/).

Only real metadata returned by the API is used.  The API key is read from
``settings.providers.pixabay_key`` and is never hardcoded here.
"""
from __future__ import annotations

import requests

from core.logger import get_logger
from core.models import SearchResult
from search.base import ProviderBase

log = get_logger("search.pixabay")

API_URL = "https://pixabay.com/api/videos/"
MAX_PER_PAGE = 200
MIN_PER_PAGE = 3

# Pixabay only supports "popular" and "latest" ordering.
_ORDER_MAP = {
    "popular": "popular",
    "new": "latest",
    "latest": "latest",
    "relevance": "popular",
}

# Quality keys returned by the API, best first.
_QUALITIES = ("large", "medium", "small", "tiny")


def _clean_tags(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(tag).strip() for tag in raw if str(tag).strip()]
    text = str(raw or "")
    return [part.strip() for part in text.split(",") if part.strip()]


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _extension(url: str, fallback: str = "mp4") -> str:
    name = str(url or "").split("?")[0].rsplit("/", 1)[-1]
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
        if ext.isalnum() and len(ext) <= 5:
            return ext
    return fallback


class PixabayProvider(ProviderBase):
    name = "pixabay"
    display_name = "Pixabay"
    site = "https://pixabay.com/"

    # ------------------------------------------------------------------- calls
    def search(self, query: str, page: int = 1, per_page: int = 20,
               order: str = "popular") -> list[SearchResult]:
        key = self.api_key()
        if not key:
            raise RuntimeError("API key is not set")
        text = (query or "").strip()
        if not text:
            raise RuntimeError("empty search query")
        params = {
            "key": key,
            "q": text[:100],  # API limit: 100 characters
            "page": max(1, _int(page) or 1),
            "per_page": max(MIN_PER_PAGE, min(MAX_PER_PAGE, _int(per_page) or 20)),
            "order": _ORDER_MAP.get(str(order or "popular").lower(), "popular"),
            "safesearch": "true",
        }
        try:
            response = self.session.get(API_URL, params=params, timeout=25)
        except requests.RequestException as error:
            raise RuntimeError(
                f"connection failed ({error.__class__.__name__})") from error

        if response.status_code == 429:
            raise RuntimeError("rate limit reached - try again in a minute")
        if response.status_code in (400, 401, 403):
            detail = ""
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    detail = str(payload.get("error") or "")
            except ValueError:
                detail = ""
            raise RuntimeError(detail or f"the API rejected the request "
                                          f"({response.status_code}) - check the API key")
        try:
            response.raise_for_status()
        except requests.RequestException as error:
            raise RuntimeError(
                f"the API returned an error ({response.status_code})") from error

        try:
            payload = response.json()
        except ValueError as error:
            raise RuntimeError("the provider returned an invalid response") from error
        hits = payload.get("hits") if isinstance(payload, dict) else None
        if not isinstance(hits, list):
            return []
        results: list[SearchResult] = []
        for hit in hits:
            parsed = self._parse_hit(hit)
            if parsed is not None:
                results.append(parsed)
        log.debug("pixabay %r page %s -> %d results", text, page, len(results))
        return results

    # ---------------------------------------------------------------- parsing
    def _parse_hit(self, hit: dict) -> SearchResult | None:
        if not isinstance(hit, dict):
            return None
        source_id = str(hit.get("id") or "").strip()
        if not source_id:
            return None
        videos = hit.get("videos") if isinstance(hit.get("videos"), dict) else {}
        available: list[tuple[str, dict]] = []
        for quality in _QUALITIES:
            info = videos.get(quality)
            if isinstance(info, dict) and info.get("url"):
                available.append((quality, info))
        if not available:
            return None

        def area(item: tuple[str, dict]) -> int:
            info = item[1]
            return _int(info.get("width")) * _int(info.get("height"))

        largest_quality, largest = max(available, key=area)
        smallest_quality, smallest = min(available, key=area)

        tags = _clean_tags(hit.get("tags"))
        name = str(hit.get("name") or "").strip()
        if name:
            title = name
        elif tags:
            title = ", ".join(tags[:3])
        else:
            title = f"Pixabay video {source_id}"

        thumbnail = ""
        for quality in ("medium", "large", "small", "tiny"):
            info = videos.get(quality)
            if isinstance(info, dict) and info.get("thumbnail"):
                thumbnail = str(info["thumbnail"])
                break
        if not thumbnail:
            thumbnail = str(largest.get("thumbnail") or smallest.get("thumbnail") or "")

        def file_entry(entry: tuple[str, dict]) -> dict:
            quality, info = entry
            return {
                "quality": quality,
                "url": str(info.get("url") or ""),
                "width": _int(info.get("width")),
                "height": _int(info.get("height")),
                "size": _int(info.get("size")),
                "thumbnail": str(info.get("thumbnail") or ""),
            }

        files = [file_entry(entry) for entry in
                 sorted(available, key=area, reverse=True)]
        best_url = str(largest.get("url") or "")
        preview_url = str(smallest.get("url") or best_url)

        return SearchResult(
            provider=self.name,
            source_id=source_id,
            title=title,
            description=str(hit.get("description") or ", ".join(tags[:8]) or ""),
            thumbnail_url=thumbnail,
            preview_url=preview_url,
            video_url=best_url,
            download_url=best_url,
            page_url=str(hit.get("pageURL") or f"https://pixabay.com/videos/id-{source_id}/"),
            author=str(hit.get("user") or ""),
            width=_int(largest.get("width")),
            height=_int(largest.get("height")),
            duration=_float(hit.get("duration")),
            format=_extension(best_url),
            tags=tags,
            files=files,
            meta={
                "views": _int(hit.get("views")),
                "downloads": _int(hit.get("downloads")),
                "likes": _int(hit.get("likes")),
                "user_url": str(hit.get("userURL") or ""),
                "type": str(hit.get("type") or ""),
                "is_ai_generated": bool(hit.get("isAiGenerated")),
            },
        )
