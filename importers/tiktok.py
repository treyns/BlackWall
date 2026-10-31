"""TikTok link importer (metadata + public video download via yt-dlp)."""
from __future__ import annotations

from importers.base import ImportLink, TIKTOK_RE, normalize_url
from importers.ytdlp import YtDlpProvider


class TikTokProvider(YtDlpProvider):
    key = "tiktok"
    label = "TikTok"

    def matches(self, url: str) -> bool:
        return bool(TIKTOK_RE.search(str(url or "")))

    def parse(self, url: str) -> ImportLink | None:
        match = TIKTOK_RE.search(str(url or ""))
        if not match:
            return None
        video_id = next((group for group in match.groups() if group), "")
        return ImportLink(self.key, video_id, normalize_url(match.group(0)))

    def video_format(self, max_height: int) -> str:
        height = max(360, int(max_height or 1080))
        return (f"bv*[ext=mp4][height<={height}]+ba[ext=m4a]/"
                f"b[ext=mp4][height<={height}]/"
                f"bv*[height<={height}]+ba/b[height<={height}]/b")
