"""Shared primitives for the TikTok / YouTube / Pinterest link importer.

Only public metadata and downloads are handled through yt-dlp. DRM-protected,
private or otherwise restricted media is reported with a human-readable reason
instead of being bypassed.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from core.logger import get_logger

log = get_logger("importers")


# --------------------------------------------------------------------------- links
@dataclass
class ImportLink:
    source: str        # "youtube" / "tiktok" / "pinterest"
    video_id: str
    url: str


YOUTUBE_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?(?:youtube\.com/"
    r"(?:watch\?(?:[^#\s]*?&)?v=|shorts/|embed/|live/|v/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})",
    re.IGNORECASE,
)
TIKTOK_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?(?:tiktok\.com/"
    r"(?:@[^/\s]+/video/(\d{8,})|t/([A-Za-z0-9]+))|"
    r"m\.tiktok\.com/v/(\d{8,})\.html|(?:vm|vt)\.tiktok\.com/([A-Za-z0-9]+))",
    re.IGNORECASE,
)
PINTEREST_RE = re.compile(
    r"(?:https?://)?(?:[a-z0-9-]+\.)*pinterest\.[a-z.]+/pin/(\d+)"
    r"|(?:https?://)?pin\.it/([A-Za-z0-9]+)",
    re.IGNORECASE,
)


def normalize_url(raw: str) -> str:
    text = str(raw or "").strip().strip("<>\"'")
    if not text:
        return ""
    if not re.match(r"^https?://", text, re.IGNORECASE):
        text = "https://" + text
    return text


def detect_link(raw: str) -> ImportLink | None:
    """Detect a YouTube/TikTok/Pinterest video link anywhere in the text."""
    text = str(raw or "").strip()
    if not text:
        return None
    match = YOUTUBE_RE.search(text)
    if match:
        return ImportLink("youtube", match.group(1), normalize_url(match.group(0)))
    match = TIKTOK_RE.search(text)
    if match:
        video_id = next((group for group in match.groups() if group), "")
        return ImportLink("tiktok", video_id, normalize_url(match.group(0)))
    match = PINTEREST_RE.search(text)
    if match:
        video_id = next((group for group in match.groups() if group), "")
        return ImportLink("pinterest", video_id, normalize_url(match.group(0)))
    return None


# --------------------------------------------------------------------------- info
@dataclass
class LinkInfo:
    source: str = ""
    video_id: str = ""
    url: str = ""
    title: str = ""
    author: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    ext: str = "mp4"
    thumbnail_url: str = ""
    thumbnail_path: str = ""
    webpage_url: str = ""
    description: str = ""
    filesize: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def aspect(self) -> str:
        from importers.processing import aspect_ratio

        return aspect_ratio(self.width, self.height)

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width} × {self.height}"
        return "—"


class ImportError(Exception):  # noqa: N818 - domain exception name
    """A user-facing import failure with a stable message key."""

    def __init__(self, message: str, code: str = "error", detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.detail = detail


class ImportCancelled(Exception):
    """Raised internally when the user cancels an import."""


def friendly_download_error(error: BaseException) -> ImportError:
    """Translate a yt-dlp / network exception into a clear message."""
    text = str(error or "")
    lower = text.lower()
    detail = text.strip()[:400]
    if any(word in lower for word in ("drm", "protected by drm")):
        return ImportError("This video is protected by DRM and cannot be imported", "drm", detail)
    if "private" in lower:
        return ImportError("This video is private and cannot be imported", "private", detail)
    if any(word in lower for word in ("sign in", "not a bot", "login", "cookies")):
        return ImportError(
            "YouTube asks to sign in for this video; import it as a file instead",
            "login", detail)
    if any(word in lower for word in ("age", "confirm your age", "age-restricted")):
        return ImportError(
            "This video is age-restricted; import it as a file instead", "age", detail)
    if any(word in lower for word in ("unavailable", "not available", "has been removed",
                                      "does not exist", "404", "not found")):
        return ImportError("This video is unavailable or has been removed", "unavailable", detail)
    if any(word in lower for word in ("403", "access denied", "forbidden")):
        return ImportError("The platform denied access to this video", "forbidden", detail)
    if "unsupported url" in lower:
        return ImportError("This link is not supported", "unsupported", detail)
    if any(word in lower for word in ("timed out", "timeout", "connection", "network",
                                      "temporary failure", "name or service")):
        return ImportError("Network error while contacting the platform", "network", detail)
    if "requested format is not available" in lower:
        return ImportError("This video has no downloadable format", "format", detail)
    if "ffmpeg" in lower:
        return ImportError("FFmpeg is required to merge the downloaded video", "ffmpeg", detail)
    return ImportError("Could not import this video", "error", detail)


# --------------------------------------------------------------------------- yt-dlp
def ytdlp_available() -> bool:
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return False
    return True


def ffmpeg_executable() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def base_ydl_options() -> dict[str, Any]:
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 1,
    }
    ffmpeg = ffmpeg_executable()
    if ffmpeg:
        options["ffmpeg_location"] = ffmpeg
    return options


def safe_filename(name: str, fallback: str = "video") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(name or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned[:80] or fallback)


def choose_best_dimensions(data: dict) -> tuple[int, int, float]:
    """Best available width/height/fps of a yt-dlp info dict."""
    width = int(data.get("width") or 0)
    height = int(data.get("height") or 0)
    fps = float(data.get("fps") or 0.0)
    if width and height:
        return width, height, fps
    formats = [f for f in (data.get("formats") or []) if f.get("vcodec") not in (None, "none")]
    if formats:
        best = max(formats, key=lambda f: (int(f.get("height") or 0),
                                           int(f.get("width") or 0)))
        width = int(best.get("width") or width or 0)
        height = int(best.get("height") or height or 0)
        fps = float(best.get("fps") or fps or 0.0)
    return width, height, fps


def is_playable_video(path: str) -> bool:
    from core.utils import is_playable

    return bool(path and os.path.exists(path) and is_playable(path))
