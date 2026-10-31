"""Steam Workshop link helper.

Steam does not expose a public direct download URL for Workshop files. This
provider fetches public metadata and imports only files that Steam has already
downloaded into the local Workshop cache. It never bypasses Steam, DRM or a
Workshop subscription.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from core.logger import get_logger
from importers.base import ImportCancelled, ImportError, ImportLink, LinkInfo, STEAM_RE, normalize_url

log = get_logger("importers.steam")

DETAILS_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
WORKSHOP_PAGE = "https://steamcommunity.com/sharedfiles/filedetails/?id={item_id}"
STEAM_PROTOCOL = "steam://url/CommunityFilePage/{item_id}"
VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi", ".ogv"}
IMAGE_EXTS = {".gif", ".webp", ".png", ".jpg", ".jpeg"}


class SteamWorkshopProvider:
    key = "steam"
    label = "Steam Workshop"

    def __init__(self) -> None:
        self.max_height = 1080

    def matches(self, url: str) -> bool:
        return bool(STEAM_RE.search(str(url or "")))

    def parse(self, url: str) -> ImportLink | None:
        match = STEAM_RE.search(str(url or ""))
        if not match:
            return None
        item_id = next((group for group in match.groups() if group), "")
        return ImportLink(self.key, item_id, normalize_url(match.group(0)))

    # ------------------------------------------------------------------ metadata
    def fetch_info(self, url: str) -> LinkInfo:
        item_id = self.parse(url).video_id if self.parse(url) else ""
        if not item_id:
            raise ImportError("This is not a valid Steam Workshop link", "steam_link")
        details = self._details(item_id)
        app_id = int(details.get("consumer_app_id") or details.get("creator_app_id") or 0)
        tags = [str(tag.get("tag", "")) for tag in (details.get("tags") or [])]
        width, height = self._resolution(tags)
        return LinkInfo(
            source=self.key,
            video_id=item_id,
            url=url,
            title=str(details.get("title") or f"Steam Workshop {item_id}"),
            author="",
            duration=0.0,
            width=width,
            height=height,
            ext="video",
            thumbnail_url=str(details.get("preview_url") or ""),
            webpage_url=WORKSHOP_PAGE.format(item_id=item_id),
            description=str(details.get("short_description") or ""),
            filesize=int(details.get("file_size") or 0),
            extra={"steam_app_id": app_id, "steam_item_id": item_id,
                   "steam_tags": tags},
        )

    def _details(self, item_id: str) -> dict:
        payload = urlencode({
            "itemcount": "1",
            "publishedfileids[0]": item_id,
        }).encode("utf-8")
        request = Request(DETAILS_URL, data=payload, headers={
            "User-Agent": "BlackWall/1.0 (Steam Workshop importer)",
            "Content-Type": "application/x-www-form-urlencoded",
        })
        try:
            with urlopen(request, timeout=25) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
        except Exception as error:  # noqa: BLE001
            raise ImportError("Could not read Steam Workshop metadata", "steam_network",
                              str(error)) from error
        details = (data.get("response", {}).get("publishedfiledetails") or [{}])[0]
        if int(details.get("result") or 0) != 1:
            raise ImportError("Steam Workshop item is unavailable", "steam_unavailable",
                              str(details.get("result")))
        return details

    @staticmethod
    def _resolution(tags: list[str]) -> tuple[int, int]:
        for tag in tags:
            match = re.search(r"(\d{3,4})\s*[x×]\s*(\d{3,4})", tag)
            if match:
                return int(match.group(1)), int(match.group(2))
        return 0, 0

    # --------------------------------------------------------------- local cache
    def download(self, url: str, dest_dir: str | os.PathLike, *,
                 max_height: int, progress: Callable[[dict], None] | None = None,
                 cancel: threading.Event | None = None) -> tuple[str, dict]:
        if cancel is not None and cancel.is_set():
            raise ImportCancelled("cancelled")
        info = self.fetch_info(url)
        app_id = int(info.extra.get("steam_app_id") or 0)
        item_id = info.video_id
        source = self._find_media(app_id, item_id)
        if source is None:
            raise ImportError(
                "This Workshop item is not downloaded. Open it in Steam, "
                "subscribe/download it, then press Import again",
                "steam_not_downloaded",
                f"app={app_id} item={item_id}")
        if cancel is not None and cancel.is_set():
            raise ImportCancelled("cancelled")
        target_dir = Path(dest_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        shutil.copy2(source, target)
        if progress is not None:
            progress({"status": "finished"})
        data = {"id": item_id, "title": info.title, "app_id": app_id}
        log.info("steam workshop local media: %s", source)
        return str(target), data

    def _find_media(self, app_id: int, item_id: str) -> Path | None:
        for library in self._steam_libraries():
            base = library / "steamapps" / "workshop" / "content"
            candidates = ([base / str(app_id) / item_id] if app_id else
                          list(base.glob(f"*/{item_id}")))
            for folder in candidates:
                if not folder.is_dir():
                    continue
                files = [path for path in folder.rglob("*")
                         if path.is_file() and path.suffix.lower() in VIDEO_EXTS | IMAGE_EXTS]
                if files:
                    videos = [path for path in files if path.suffix.lower() in VIDEO_EXTS]
                    pool = videos or files
                    return max(pool, key=lambda path: path.stat().st_size)
        return None

    @staticmethod
    def _steam_libraries() -> list[Path]:
        roots: list[Path] = []
        try:
            import winreg

            for hive, key_name in (
                    (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
                try:
                    with winreg.OpenKey(hive, key_name) as key:
                        for value_name in ("SteamPath", "InstallPath"):
                            try:
                                value, _ = winreg.QueryValueEx(key, value_name)
                                if value:
                                    roots.append(Path(str(value)))
                            except OSError:
                                pass
                except OSError:
                    pass
        except Exception:  # noqa: BLE001
            pass
        roots.extend([
            Path(r"C:\Program Files (x86)\Steam"),
            Path(r"C:\Program Files\Steam"),
        ])
        libraries: list[Path] = []
        for root in roots:
            if not root.is_dir():
                continue
            for path in (root, *SteamWorkshopProvider._vdf_libraries(root)):
                if path.is_dir() and path not in libraries:
                    libraries.append(path)
        return libraries

    @staticmethod
    def _vdf_libraries(root: Path) -> list[Path]:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            return []
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        paths: list[Path] = []
        for raw in re.findall(r'"path"\s+"([^"]+)"', text):
            path = Path(raw.replace("\\\\", "\\"))
            if path.is_dir():
                paths.append(path)
        return paths
