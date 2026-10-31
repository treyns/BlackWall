"""Pinterest link importer (public video pins via yt-dlp)."""
from __future__ import annotations

from importers.base import ImportError, ImportLink, PINTEREST_RE, normalize_url
from importers.ytdlp import YtDlpProvider


class PinterestProvider(YtDlpProvider):
    key = "pinterest"
    label = "Pinterest"

    def matches(self, url: str) -> bool:
        return bool(PINTEREST_RE.search(str(url or "")))

    def parse(self, url: str) -> ImportLink | None:
        match = PINTEREST_RE.search(str(url or ""))
        if not match:
            return None
        video_id = next((group for group in match.groups() if group), "")
        return ImportLink(self.key, video_id, normalize_url(match.group(0)))

    def video_format(self, max_height: int) -> str:
        height = max(360, int(max_height or 1080))
        # Pinterest gives one progressive MP4 plus HLS variants; prefer MP4.
        return (f"bv*[ext=mp4][height<={height}]+ba[ext=m4a]/"
                f"b[ext=mp4][height<={height}]/"
                f"bv*[height<={height}]+ba/b[height<={height}]/b")

    def fetch_info(self, url: str):
        try:
            return super().fetch_info(url)
        except ImportError as error:
            text = f"{error.message} {error.detail}".lower()
            if any(word in text for word in ("does not contain a video", "no video",
                                             "unsupported", "not a video")):
                raise ImportError(
                    "This Pinterest pin does not contain a video; import the "
                    "image as a file instead", "image", error.detail) from error
            raise
