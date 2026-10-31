"""Video probing and FFmpeg processing for imported wallpapers."""
from __future__ import annotations

import math
import os
import subprocess
import threading
from pathlib import Path
from typing import Callable

from config import paths
from core import utils
from core.logger import get_logger
from importers.base import ImportCancelled, ImportError, ffmpeg_executable

log = get_logger("importers.processing")

COMMON_ASPECTS = {
    (16, 9): "16:9",
    (9, 16): "9:16",
    (4, 3): "4:3",
    (3, 4): "3:4",
    (21, 9): "21:9",
    (1, 1): "1:1",
    (2, 1): "2:1",
    (2, 3): "2:3",
}


def aspect_ratio(width: int, height: int) -> str:
    width, height = int(width or 0), int(height or 0)
    if width <= 0 or height <= 0:
        return ""
    divisor = math.gcd(width, height) or 1
    simple = (width // divisor, height // divisor)
    if simple in COMMON_ASPECTS:
        return COMMON_ASPECTS[simple]
    ratio = width / height
    for (w, h), label in COMMON_ASPECTS.items():
        if abs(ratio - w / h) < 0.015:
            return label
    return f"{simple[0]}:{simple[1]}"


def probe_video(path: str | os.PathLike) -> dict:
    """Probe a video using the same OpenCV path as the rest of the app."""
    info = utils.probe_media(path)
    info["aspect"] = aspect_ratio(info.get("width", 0), info.get("height", 0))
    info.setdefault("fps", 0.0)
    info["compatible"] = format_compatible(str(path))
    return info


def format_compatible(path: str) -> bool:
    from config.constants import VIDEO_EXTS

    ext = Path(path).suffix.lower()
    if ext not in VIDEO_EXTS:
        return False
    return Path(path).is_file()


def target_dimensions(source_width: int, source_height: int,
                      monitors: list | None) -> tuple[int, int]:
    """Largest monitor size, never upscaling the source."""
    width = int(source_width or 0)
    height = int(source_height or 0)
    if width <= 0 or height <= 0:
        return 1920, 1080
    max_w = max([int(getattr(m, "width", 0) or 0) for m in (monitors or [])] or [0])
    max_h = max([int(getattr(m, "height", 0) or 0) for m in (monitors or [])] or [0])
    if max_w <= 0:
        max_w = 1920
    if max_h <= 0:
        max_h = 1080
    # A wallpaper with "cover" must cover the whole monitor, so the source is
    # reduced by the larger of the two ratios (never upscaled).
    scale = min(1.0, max(max_w / width, max_h / height))
    return max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)


def needs_optimization(info: dict, target_width: int, target_height: int) -> bool:
    width = int(info.get("width") or 0)
    height = int(info.get("height") or 0)
    if width > target_width + 2 or height > target_height + 2:
        return True
    fps = float(info.get("fps") or 0.0)
    if fps > 61:
        return True
    return not bool(info.get("compatible", True))


def free_space_ok(required_bytes: int, path: str | os.PathLike | None = None) -> bool:
    try:
        usage = __import__("shutil").disk_usage(str(path or paths.MEDIA_DIR))
        return usage.free >= max(0, int(required_bytes))
    except OSError:
        return True


def has_audio_track(path: str) -> bool:
    """Return True when FFmpeg reports at least one audio stream."""
    ffmpeg = ffmpeg_executable()
    if not ffmpeg or not path or not os.path.exists(path):
        return False
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", path],
            capture_output=True, text=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "Audio:" in (result.stderr or "")
    except Exception:  # noqa: BLE001
        return False


def decode_errors(path: str) -> str:
    """Return FFmpeg decoder errors (empty string when the file is clean)."""
    ffmpeg = ffmpeg_executable()
    if not ffmpeg or not path or not os.path.exists(path):
        return ""
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-v", "error", "-i", path, "-f", "null", "-"],
            capture_output=True, text=True, timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return (result.stderr or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def ensure_playable_video(path: str,
                          progress: Callable[[int], None] | None = None) -> str:
    """Validate the decode chain and re-encode a damaged download if needed.

    Some TikTok streams contain malformed H.264 access units: the container and
    metadata look fine, but Qt/FFmpeg refuses to play them. A tolerant re-encode
    turns such a file into a clean H.264/AAC copy before it reaches the library.
    """
    errors = decode_errors(path)
    if not errors:
        return path
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        raise ImportError("FFmpeg is not available", "ffmpeg")
    log.warning("video decode errors in %s: %s", path, errors[:200])
    if progress is not None:
        progress(0)
    source = Path(path)
    fixed = source.with_name(f"{source.stem}_fixed.mp4")
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-err_detect", "ignore_err",
        "-i", str(source),
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(fixed),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=600,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode != 0 or not fixed.exists() or fixed.stat().st_size <= 0:
        fixed.unlink(missing_ok=True)
        raise ImportError("The downloaded video is damaged and could not be repaired",
                          "decode", (result.stderr or "").strip()[:300])
    remaining = decode_errors(str(fixed))
    if remaining:
        fixed.unlink(missing_ok=True)
        raise ImportError("The downloaded video is damaged and could not be repaired",
                          "decode", remaining[:300])
    if progress is not None:
        progress(100)
    log.info("repaired damaged video: %s -> %s", source, fixed)
    return str(fixed)


def make_thumbnail(source: str, dest: str, position: float = 1.0) -> str | None:
    """Extract one frame as a JPEG thumbnail."""
    try:
        import cv2
        from PIL import Image

        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            return None
        try:
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, position) * 1000.0)
            ok, frame = cap.read()
            if not ok:
                ok, frame = cap.read()
            if not ok or frame is None:
                return None
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            image = Image.fromarray(rgb)
            image.thumbnail((640, 640))
            image.save(dest, "JPEG", quality=86)
            return dest
        finally:
            cap.release()
    except Exception as error:  # noqa: BLE001
        log.warning("thumbnail failed for %s: %s", source, error)
        return None


def optimize_video(source: str, dest: str, target_width: int, target_height: int,
                   source_fps: float = 0.0, duration: float = 0.0,
                   progress: Callable[[int], None] | None = None,
                   cancel: threading.Event | None = None) -> str:
    """Create a monitor-sized H.264 copy; the original file is untouched."""
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        raise ImportError("FFmpeg is not available", "ffmpeg")
    source_info = probe_video(source)
    width = int(source_info.get("width") or target_width)
    height = int(source_info.get("height") or target_height)
    scale = min(1.0, max(2, target_width) / max(1, width),
                max(2, target_height) / max(1, height))
    out_w = max(2, int(width * scale) // 2 * 2)
    out_h = max(2, int(height * scale) // 2 * 2)
    target_fps = min(60.0, float(source_fps or source_info.get("fps") or 30.0)) or 30.0
    total_duration = float(duration or source_info.get("duration") or 0.0)

    destination = Path(dest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(".part.mp4")
    tmp.unlink(missing_ok=True)
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-nostats",
        "-progress", "pipe:1",
        "-i", source,
        "-map", "0:v:0", "-map", "0:a?",
        "-vf", f"scale={out_w}:{out_h}:flags=lanczos",
        "-r", f"{target_fps:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "128k",
        str(tmp),
    ]
    log.info("optimizing %s -> %s (%dx%d, %.1f fps)", source, destination, out_w, out_h,
             target_fps)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, creationflags=creationflags)
    try:
        assert process.stdout is not None
        for line in process.stdout:
            if cancel is not None and cancel.is_set():
                process.terminate()
                raise ImportCancelled("Import cancelled")
            if progress is not None and line.startswith("out_time_us="):
                try:
                    seconds = int(line.split("=", 1)[1]) / 1_000_000.0
                except (TypeError, ValueError):
                    continue
                if total_duration > 0:
                    progress(max(0, min(100, int(seconds / total_duration * 100))))
        process.wait(timeout=30)
        errors = process.stderr.read() if process.stderr is not None else ""
        if cancel is not None and cancel.is_set():
            raise ImportCancelled("Import cancelled")
        if process.returncode != 0:
            raise ImportError("Could not optimize the video", "optimize",
                              (errors or "ffmpeg failed").strip()[:400])
        if not tmp.exists() or tmp.stat().st_size <= 0:
            raise ImportError("The optimized copy is empty", "optimize")
        tmp.replace(destination)
        tmp.unlink(missing_ok=True)
        if progress is not None:
            progress(100)
        return str(destination)
    except ImportCancelled:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        tmp.unlink(missing_ok=True)
        raise
    except ImportError:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        tmp.unlink(missing_ok=True)
        raise
    except Exception as error:  # noqa: BLE001
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        tmp.unlink(missing_ok=True)
        log.exception("optimization failed for %s", source)
        raise ImportError("Could not optimize the video", "optimize", str(error)[:300]) from error


def optimized_path_for(source: str, media_id: int, target_width: int) -> str:
    name = f"{Path(source).stem}_{media_id}_{target_width}p.mp4"
    from importers.base import safe_filename

    return str(paths.OPTIMIZED_DIR / safe_filename(name, f"video_{media_id}_{target_width}p.mp4"))
