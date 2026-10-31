"""Static constants: identity, palette, performance presets, media types."""
from __future__ import annotations

APP_NAME = "BlackWall"
APP_TITLE = "BlackWall — Live Wallpapers"
APP_VERSION = "1.0.0"

# --- Premium Dark UI palette (yellow accent, per specification) ---------------
COLORS = {
    "bg": "#101113",
    "sidebar": "#151619",
    "card": "#1C1E22",
    "surface": "#24262A",
    "accent": "#F2C72E",
    "accent_light": "#FFE16A",
    "text": "#F2F2F2",
    "text_dim": "#92959B",
    "border": "#303238",
    "error": "#E05252",
    "success": "#55C58A",
    "warning": "#E8A33D",
    "shadow": "#050506",
    # derived
    "accent_text": "#101113",
    "hover": "#26282D",
    "pressed": "#2E3036",
    "selection": "#33352B",
}

# Alternative accent requested by the user (black/violet), switchable in Settings.
ACCENTS = {
    "yellow": {
        "label": "Yellow",
        "accent": "#F2C72E",
        "accent_light": "#FFE16A",
        "accent_text": "#101113",
        "selection": "#33352B",
    },
    "violet": {
        "label": "Violet",
        "accent": "#8B5CF6",
        "accent_light": "#B79CFF",
        "accent_text": "#12101A",
        "selection": "#2A2440",
    },
}

FONT_FAMILY = "Segoe UI"

# --- Aurora redesign ---------------------------------------------------------
# Pure-black premium palette from BlackWall_Aurora_Palette.txt. Classic keeps
# the original Premium Dark colours untouched.
AURORA_COLORS = {
    "bg": "#000000",
    "sidebar": "#080808",
    "card": "#141414",
    "surface": "#1B1B1B",
    "border": "#292929",
    "border_hover": "#3A3A3A",
    "hover": "#1F1F1F",
    "pressed": "#262626",
    "text": "#FFFFFF",
    "text_dim": "#B3B3B3",
    "text_faint": "#707070",
    "error": "#FF4D6D",
    "success": "#55C58A",
    "warning": "#FFB000",
    "shadow": "#000000",
}

AURORA_ACCENTS = {
    "purple": {
        "label": "Electric Purple",
        "accent": "#8B35FF",
        "accent_light": "#B06BFF",
        "accent_text": "#FFFFFF",
        "selection": "#241238",
    },
    "cyan": {
        "label": "Laser Cyan",
        "accent": "#00C8FF",
        "accent_light": "#5EDDFF",
        "accent_text": "#001014",
        "selection": "#0B2630",
    },
    "pink": {
        "label": "Hot Pink",
        "accent": "#FF2D75",
        "accent_light": "#FF6B9D",
        "accent_text": "#FFFFFF",
        "selection": "#2E1220",
    },
    "lime": {
        "label": "Neon Lime",
        "accent": "#A6FF00",
        "accent_light": "#C6FF5E",
        "accent_text": "#0A1400",
        "selection": "#1F2A08",
    },
    "amber": {
        "label": "Amber",
        "accent": "#FFB000",
        "accent_light": "#FFD166",
        "accent_text": "#1A1200",
        "selection": "#2A2008",
    },
}

THEMES = {
    "aurora": {"label": "Aurora"},
    "classic": {"label": "Classic · Premium Dark"},
}
ACCENTS_BY_THEME = {
    "aurora": AURORA_ACCENTS,
    "classic": ACCENTS,
}
DEFAULT_THEME = "aurora"
DEFAULT_ACCENT = "purple"

# --- Performance modes -------------------------------------------------------
PERFORMANCE_MODES = {
    "eco": {"fps": 15, "label": "Economy", "description": "15 FPS · minimal load · pause in games"},
    "balanced": {"fps": 30, "label": "Balanced", "description": "30 FPS · quality and load in balance"},
    "quality": {"fps": 60, "label": "Quality", "description": "up to 60 FPS when the system keeps up"},
}
PERFORMANCE_MODE_ORDER = ["eco", "balanced", "quality"]

# --- Media types -------------------------------------------------------------
VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi", ".ogv"}
ANIMATED_EXTS = {".gif", ".webp"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
PLAYABLE_EXTS = VIDEO_EXTS | ANIMATED_EXTS | IMAGE_EXTS

FIT_MODES = {
    "cover": "Fill screen (crop edges)",
    "blur": "Blurred background",
    "contain": "Fit whole picture",
    "stretch": "Stretch (no aspect)",
}
FIT_MODE_ORDER = ["cover", "blur", "contain", "stretch"]

# --- Link import (TikTok / YouTube) ------------------------------------------
IMPORT_SOURCES = {
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "pinterest": "Pinterest",
}
IMPORT_MAX_HEIGHTS = [
    (480, "480p"),
    (720, "720p"),
    (1080, "1080p"),
    (1440, "1440p (2K)"),
    (2160, "2160p (4K)"),
    (4320, "4320p (8K)"),
]
DEFAULT_IMPORT_MAX_HEIGHT = 1080

# --- Manual video quality (used when automatic quality reduction is off) ------
# The key is the target video width; "original" means the source file itself.
VIDEO_QUALITY_OPTIONS = [
    ("original", "Original"),
    ("4320p", "4320p (8K)"),
    ("2160p", "2160p (4K)"),
    ("1440p", "1440p (2K)"),
    ("1080p", "1080p (Full HD)"),
    ("720p", "720p (HD)"),
    ("480p", "480p (SD)"),
]
VIDEO_QUALITY_WIDTHS = {
    "original": 0,
    "4320p": 7680,
    "2160p": 3840,
    "1440p": 2560,
    "1080p": 1920,
    "720p": 1280,
    "480p": 854,
}
VIDEO_QUALITY_LABELS = {
    "original": "Original",
    "4320p": "4320p (8K)",
    "2160p": "2160p (4K)",
    "1440p": "1440p (2K)",
    "1080p": "1080p (Full HD)",
    "720p": "720p (HD)",
    "480p": "480p (SD)",
}

# --- Search categories (id, English label, provider query) -------------------
CATEGORIES = [
    ("space", "Space", "space galaxy nebula"),
    ("nature", "Nature", "nature landscape waterfall"),
    ("anime", "Anime", "anime night rain"),
    ("cars", "Cars", "car cinematic supercar"),
    ("cities", "Cities", "city night street"),
    ("cyberpunk", "Cyberpunk", "cyberpunk neon city"),
    ("games", "Games", "game fantasy landscape"),
    ("fantasy", "Fantasy", "fantasy magical landscape"),
    ("abstract", "Abstract", "abstract neon background"),
    ("tech", "Technology", "technology digital background"),
    ("ocean", "Ocean", "ocean underwater"),
    ("architecture", "Architecture", "architecture building"),
]
CATEGORY_LABELS = {cid: label for cid, label, _ in CATEGORIES}
CATEGORY_QUERY = {cid: query for cid, _, query in CATEGORIES}

RESOLUTIONS = [
    ("any", "Any resolution", None),
    ("720p", "720p", (960, 720)),
    ("1080p", "1080p", (1600, 900)),
    ("1440p", "1440p", (2400, 1300)),
    ("4k", "4K", (3200, 1700)),
]
RESOLUTION_MIN = {rid: min_size for rid, _, min_size in RESOLUTIONS}

DURATION_FILTERS = [
    ("any", "Any duration", (0, 10 ** 9)),
    ("short", "Up to 10 s", (0, 10)),
    ("medium", "10–30 s", (10, 30)),
    ("long", "Over 30 s", (30, 10 ** 9)),
]

SORT_OPTIONS = [
    ("relevance", "Relevance"),
    ("popular", "Popularity"),
    ("new", "Newest"),
    ("duration", "Duration"),
    ("resolution", "Resolution"),
]

PROVIDERS = {
    "pixabay": {
        "name": "Pixabay",
        "site": "https://pixabay.com/",
        "api_docs": "https://pixabay.com/api/docs/",
        "key_help": "Pixabay: register free at pixabay.com, then copy the API key from the API docs page.",
    },
    "pexels": {
        "name": "Pexels",
        "site": "https://www.pexels.com/",
        "api_docs": "https://www.pexels.com/api/",
        "key_help": "Pexels: create a free account at pexels.com/api and copy the API key.",
    },
}

# --- UI metrics --------------------------------------------------------------
WINDOW_DEFAULT_SIZE = (1380, 860)
WINDOW_MIN_SIZE = (1120, 700)
SIDEBAR_WIDTH = 244
SIDEBAR_COLLAPSED_WIDTH = 76
CARD_RADIUS = 14
BUTTON_RADIUS = 10

# --- Recommendations ---------------------------------------------------------
# "Editor's choice" is a curated selection of REAL provider results: queries
# curated by us, videos fetched live from the providers.
CURATED_QUERIES = [
    "cyberpunk city night",
    "space nebula 4k",
    "japanese street rain",
    "mountain sunrise",
    "deep ocean underwater",
    "neon city abstract",
]

RECOMMENDATION_SECTIONS = [
    ("popular", "Popular now"),
    ("new", "New videos"),
    ("recommended", "Recommended for you"),
    ("curated", "Editor's choice"),
]

# --- Tray / phone-home -------------------------------------------------------
UPDATE_CHECK_URL = ""  # no update server yet; the check reports "no data" honestly
