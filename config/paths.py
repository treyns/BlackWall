"""Filesystem layout for BlackWall.

Everything the app writes lives inside the project directory so the whole
installation can be copied or removed as one folder.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # Packaged BlackWall.exe: keep user data next to the executable, while
    # read-only assets are unpacked by PyInstaller into _MEIPASS.
    APP_ROOT = Path(sys.executable).resolve().parent
    ASSETS_DIR = Path(getattr(sys, "_MEIPASS", APP_ROOT)) / "assets"
else:
    APP_ROOT = Path(__file__).resolve().parent.parent
    ASSETS_DIR = APP_ROOT / "assets"

DATA_DIR = APP_ROOT / "data"
CACHE_DIR = APP_ROOT / "cache"
LOGS_DIR = APP_ROOT / "logs"
MEDIA_DIR = APP_ROOT / "media"

THUMBNAILS_DIR = CACHE_DIR / "thumbnails"
REMOTE_THUMBNAILS_DIR = CACHE_DIR / "remote_thumbnails"
SEARCH_CACHE_DIR = CACHE_DIR / "search"

DEFAULT_LIBRARY_DIR = MEDIA_DIR / "library"
DEFAULT_DOWNLOAD_DIR = MEDIA_DIR / "downloads"
IMPORTS_DIR = MEDIA_DIR / "imports"
OPTIMIZED_DIR = MEDIA_DIR / "optimized"

SETTINGS_FILE = DATA_DIR / "settings.json"
DATABASE_FILE = DATA_DIR / "blackwall.db"
LOG_FILE = LOGS_DIR / "blackwall.log"
ICON_FILE = ASSETS_DIR / "icon.ico"
ICON_PNG = ASSETS_DIR / "icon.png"

I18N_DIR = ASSETS_DIR / "i18n"


def ensure_dirs() -> None:
    """Create every directory the application may write to."""
    for path in (
        DATA_DIR,
        CACHE_DIR,
        LOGS_DIR,
        ASSETS_DIR,
        MEDIA_DIR,
        THUMBNAILS_DIR,
        REMOTE_THUMBNAILS_DIR,
        SEARCH_CACHE_DIR,
        DEFAULT_LIBRARY_DIR,
        DEFAULT_DOWNLOAD_DIR,
        IMPORTS_DIR,
        OPTIMIZED_DIR,
    ):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def expand(path: str | os.PathLike | None) -> Path:
    """Expand ``%VAR%`` and ``~`` and return an absolute Path."""
    if not path:
        return Path("")
    raw = os.path.expandvars(str(path))
    return Path(os.path.abspath(os.path.expanduser(raw)))
