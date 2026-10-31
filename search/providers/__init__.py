"""Search provider plugins.

Every online wallpaper source is a separate module under this package; the
search manager loads them independently so a new source can be added without
touching the UI.  Keys are always read from settings - never from source code.
"""
from __future__ import annotations

from search.providers.pexels import PexelsProvider
from search.providers.pixabay import PixabayProvider

# Order in which the providers are shown to the user.
PROVIDER_CLASSES = (PixabayProvider, PexelsProvider)

__all__ = ["PROVIDER_CLASSES", "PexelsProvider", "PixabayProvider"]
