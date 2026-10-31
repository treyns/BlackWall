"""Pexels video provider (official API: https://www.pexels.com/api/documentation/).

Only real metadata returned by the API is used.  The API key is read from
``settings.providers.pexels_key`` and is never hardcoded here.
"""
from __future__ import annotations

import re

import requests

from core.logger import get_logger
from core.models import SearchResult
from search.base import ProviderBase

log = get_logger("search.pexels")

API_URL = "https://api.pexels.com/videos/search"
MAX_PER_PAGE = 80  # Pexels allows 1..80 per page
_TRAILING_ID = re.compile(r"[-_]\d+$")


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


def _title_from_url(url: str, source_id: str) -> str:
    """Build a readable name from the real Pexels page slug (no invented data)."""
    path = str(url or "").split("?")[0].rstrip("/")
    slug = path.rsplit("/", 1)[-1] if path else ""
    slug = _TRAILING_ID.sub("", slug)
    words = [part for part in re.split(r"[-_]+", slug) if part]
    if words:
        text = " ".join(words)
        return text[:1].upper() + text[1:]
    return f"Pexels video {source_id}"


class PexelsProvider(ProviderBase):
    name = "pexels"
    display_name = "Pexels"
    site = "https://www.pexels.com/"

    # ------------------------------------------------------------------- calls
    def search(self, query: str, page: int = 1, per_page: int = 20,
               order: str = "popular") -> list[SearchResult]:  # noqa: ARG002 - API has no order
        key = self.api_key()
        if not key:
            raise RuntimeError("API key is not set")
        text = (query or "").strip()
        if not text:
            raise RuntimeError("empty search query")
        params = {
            "query": text[:100],
            "page": max(1, _int(page) or 1),
            "per_page": max(1, min(MAX_PER_PAGE, _int(per_page) or 20)),
        }
        try:
            response = self.session.get(
                API_URL, params=params, timeout=25,
                headers={"Authorization": key},
            )
        except requests.RequestException as error:
            raise RuntimeError(
                f"connection failed ({error.__class__.__name__})") from error

        if response.status_code == 401:
            raise RuntimeError("the API key was rejected - check it in Settings")
        if response.status_code == 403:
            raise RuntimeError("access to the Pexels API is forbidden for this key")
        if response.status_code == 429:
            raise RuntimeError("rate limit reached - try again later")
        try:
            response.raise_for_status()
        except requests.RequestException as error:
            raise RuntimeError(
                f"the API returned an error ({response.status_code})") from error

        try:
            payload = response.json()
        except ValueError as error:
            raise RuntimeError("the provider returned an invalid response") from error
        videos = payload.get("videos") if isinstance(payload, dict) else None
        if not isinstance(videos, list):
            return []
        results: list[SearchResult] = []
        for video in videos:
            parsed = self._parse_video(video)
            if parsed is not None:
                results.append(parsed)
        log.debug("pexels %r page %s -> %d results", text, page, len(results))
        return results

    # ---------------------------------------------------------------- parsing
    def _parse_video(self, video: dict) -> SearchResult | None:
        if not isinstance(video, dict):
            return None
        source_id = str(video.get("id") or "").strip()
        if not source_id:
            return None
        raw_files = video.get("video_files")
        if not isinstance(raw_files, list):
            return None
        files: list[dict] = []
        for entry in raw_files:
            if not isinstance(entry, dict):
                continue
            link = str(entry.get("link") or "")
            if not link:
                continue
            files.append({
                "quality": str(entry.get("quality") or ""),
                "url": link,
                "file_type": str(entry.get("file_type") or ""),
                "width": _int(entry.get("width")),
                "height": _int(entry.get("height")),
                "fps": _float(entry.get("fps")),
            })
        if not files:
            return None

        def area(entry: dict) -> int:
            return entry["width"] * entry["height"]

        best = max(files, key=area)
        playable = [entry for entry in files
                    if entry["file_type"].startswith("video/") or
                    _extension(entry["url"]) in ("mp4", "webm")]
        playable = playable or files
        # Preview: the smallest file that is still reasonably sharp.
        preview_candidates = [entry for entry in playable if entry["width"] >= 640]
        preview = min(preview_candidates or playable, key=area)

        page_url = str(video.get("url") or f"https://www.pexels.com/video/{source_id}/")
        title = _title_from_url(page_url, source_id)
        user = video.get("user") if isinstance(video.get("user"), dict) else {}
        image = str(video.get("image") or "")
        if not image:
            pictures = video.get("video_pictures")
            if isinstance(pictures, list) and pictures:
                first = pictures[0]
                if isinstance(first, dict):
                    image = str(first.get("picture") or "")
        tags_raw = video.get("tags")
        tags = [str(tag).strip() for tag in tags_raw
                if str(tag).strip()] if isinstance(tags_raw, list) else []

        return SearchResult(
            provider=self.name,
            source_id=source_id,
            title=title,
            description=", ".join(tags),
            thumbnail_url=image,
            preview_url=str(preview["url"]),
            video_url=str(best["url"]),
            download_url=str(best["url"]),
            page_url=page_url,
            author=str(user.get("name") or ""),
            width=_int(video.get("width")) or best["width"],
            height=_int(video.get("height")) or best["height"],
            duration=_float(video.get("duration")),
            format=_extension(str(best["url"])),
            tags=tags,
            files=files,
            meta={
                "user_url": str(user.get("url") or ""),
                "avg_color": str(video.get("avg_color") or ""),
                "quality": str(best.get("quality") or ""),
            },
        )
