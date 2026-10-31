"""YouTube link importer (metadata + public video download via yt-dlp)."""
from __future__ import annotations

from importers.base import ImportLink, YOUTUBE_RE, normalize_url
from importers.ytdlp import YtDlpProvider


class YouTubeProvider(YtDlpProvider):
    key = "youtube"
    label = "YouTube"

    def matches(self, url: str) -> bool:
        return bool(YOUTUBE_RE.search(str(url or "")))

    def parse(self, url: str) -> ImportLink | None:
        match = YOUTUBE_RE.search(str(url or ""))
        if not match:
            return None
        return ImportLink(self.key, match.group(1), normalize_url(match.group(0)))

    def video_format(self, max_height: int) -> str:
        height = max(360, int(max_height or 1080))
        # Prefer MP4 + M4A so the merged file is immediately usable by Qt/FFmpeg.
        return (f"bv*[ext=mp4][height<={height}]+ba[ext=m4a]/"
                f"b[ext=mp4][height<={height}]/"
                f"bv*[height<={height}]+ba/b[height<={height}]/b")
