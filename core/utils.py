"""Formatting, media probing and small OS helpers."""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

from core.models import media_kind


# --------------------------------------------------------------------- format
def human_size(num: float | int | None) -> str:
    if not num or num <= 0:
        return "—"
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def human_duration(seconds: float | None) -> str:
    if not seconds or seconds <= 0:
        return "—"
    total = int(round(seconds))
    if total < 3600:
        return f"{total // 60}:{total % 60:02d}"
    return f"{total // 3600}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def human_eta(seconds: float | None) -> str:
    if not seconds or seconds <= 0 or seconds > 3600 * 24:
        return "—"
    total = int(round(seconds))
    if total < 60:
        return f"{total} s"
    if total < 3600:
        return f"{total // 60} min {total % 60:02d} s"
    return f"{total // 3600} h {(total % 3600) // 60:02d} min"


def human_speed(bytes_per_sec: float | None) -> str:
    if not bytes_per_sec or bytes_per_sec <= 0:
        return "—"
    return f"{human_size(bytes_per_sec)}/s"


def safe_filename(name: str, fallback: str = "wallpaper") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned or fallback)[:120]


def uid_for_url(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------- media
def probe_media(path: str | os.PathLike) -> dict:
    """Read real metadata (resolution/duration/fps) of a media file.

    Returns a dict with width, height, duration, fps, format, kind.
    Never raises: on failure fields stay zero/empty.
    """
    path = str(path)
    info = {
        "width": 0,
        "height": 0,
        "duration": 0.0,
        "fps": 0.0,
        "format": Path(path).suffix.lstrip(".").upper(),
        "kind": media_kind(path),
        "size_bytes": 0,
    }
    try:
        info["size_bytes"] = os.path.getsize(path)
    except OSError:
        pass

    kind = info["kind"]
    if kind == "video":
        try:
            import cv2  # local import: heavy module, only needed here

            cap = cv2.VideoCapture(path)
            if cap.isOpened():
                info["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
                info["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
                info["fps"] = fps if 0 < fps < 1000 else 0.0
                frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                if info["fps"] > 0 and frames > 0:
                    info["duration"] = frames / info["fps"]
            cap.release()
        except Exception:  # noqa: BLE001 - probing must never crash the app
            pass
    else:
        try:
            from PIL import Image

            with Image.open(path) as im:
                info["width"], info["height"] = im.size
                frames = getattr(im, "n_frames", 1)
                duration = float(im.info.get("duration", 0) or 0) / 1000.0
                info["duration"] = duration * max(1, frames) if frames > 1 else 0.0
                info["animated"] = frames > 1
                info["kind"] = "animation" if frames > 1 else "image"
        except Exception:  # noqa: BLE001
            pass
    return info


def thumbnail_for(path: str | os.PathLike, out_path: str | os.PathLike,
                  width: int = 640) -> bool:
    """Write a JPEG thumbnail for a video/image/animation. Returns success."""
    path, out_path = str(path), str(out_path)
    if not os.path.exists(path):
        return False
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    except OSError:
        return False
    kind = media_kind(path)
    try:
        from PIL import Image

        if kind == "video":
            import cv2

            cap = cv2.VideoCapture(path)
            ok, frame = cap.read()
            if ok and frame is not None:
                height = max(1, int(frame.shape[0] * width / max(1, frame.shape[1])))
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
                cv2.imwrite(out_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
            cap.release()
            return ok
        with Image.open(path) as im:
            im.seek(0)
            im = im.convert("RGB")
            ratio = width / max(1, im.width)
            im = im.resize((width, max(1, int(im.height * ratio))), Image.LANCZOS)
            im.save(out_path, "JPEG", quality=88)
            return True
    except Exception:  # noqa: BLE001
        return False


def is_playable(path: str | os.PathLike) -> bool:
    from config.constants import PLAYABLE_EXTS

    return Path(path).suffix.lower() in PLAYABLE_EXTS


# ------------------------------------------------------------------------- os
def open_in_explorer(path: str) -> None:
    """Open a file with the default app / reveal it in Explorer."""
    if not path or not os.path.exists(path):
        return
    if os.name == "nt":
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except OSError:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        subprocess.Popen(["xdg-open", path])


def reveal_in_explorer(path: str) -> None:
    if os.name == "nt" and path and os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])


def open_url(url: str) -> None:
    if not url:
        return
    try:
        import webbrowser

        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass


def free_space_gb(path: str | os.PathLike) -> float:
    try:
        usage = os.statvfs(str(path)) if hasattr(os, "statvfs") else None
        if usage:
            return usage.f_bavail * usage.f_frsize / (1024 ** 3)
        import shutil

        return shutil.disk_usage(os.path.abspath(str(path))).free / (1024 ** 3)
    except OSError:
        return 0.0


def dir_size_bytes(path: str | os.PathLike) -> int:
    total = 0
    try:
        for root, _dirs, files in os.walk(str(path)):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def resource_path(*parts: str) -> str:
    base = Path(__file__).resolve().parent.parent
    return str(base.joinpath(*parts))


def is_windows() -> bool:
    return sys.platform == "win32"
