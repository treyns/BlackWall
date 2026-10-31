"""Merge several videos into one wallpaper with automatic or manual cuts."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from config import paths
from core import utils
from core.database import now_iso
from core.logger import get_logger
from core.models import MediaItem
from importers.base import ImportCancelled, ImportError, ffmpeg_executable, safe_filename
from importers.processing import (
    aspect_ratio,
    free_space_ok,
    has_audio_track,
    make_thumbnail,
    probe_video,
)

log = get_logger("merge")


@dataclass
class MergeClip:
    path: str
    start_frame: int = 0
    end_frame: int = 0          # 0 = until the end
    fps: float = 0.0
    duration: float = 0.0
    width: int = 0
    height: int = 0


@dataclass
class MergeProject:
    clips: list[MergeClip] = field(default_factory=list)
    title: str = ""
    width: int = 1920
    height: int = 1080
    fps: int = 30
    manual: bool = False


class MergeManager(QObject):
    started = Signal()
    phase = Signal(str)
    progress = Signal(int, str)
    finished = Signal(int)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, db, settings, library, monitors, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.settings = settings
        self.library = library
        self.monitors = monitors
        self._cancel = threading.Event()
        self._busy = False
        self._lock = threading.Lock()

    @property
    def busy(self) -> bool:
        return self._busy

    def cancel(self) -> None:
        self._cancel.set()

    def merge(self, project: MergeProject) -> None:
        if len([clip for clip in project.clips if clip.path]) < 2:
            self.failed.emit("Add at least two videos")
            return
        with self._lock:
            if self._busy:
                self.failed.emit("Another operation is already running")
                return
            self._busy = True
        self._cancel.clear()
        self.started.emit()
        threading.Thread(target=self._merge_worker, args=(project,), daemon=True,
                         name="merge-videos").start()

    def _merge_worker(self, project: MergeProject) -> None:
        temp_dir = paths.CACHE_DIR / f"merge_{int(time.time())}_{os.getpid()}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            clips = [clip for clip in project.clips if clip.path and os.path.exists(clip.path)]
            if len(clips) < 2:
                raise ImportError("Add at least two videos", "empty")
            total_seconds = 0.0
            for clip in clips:
                info = probe_video(clip.path)
                clip.width = int(info.get("width") or 0)
                clip.height = int(info.get("height") or 0)
                clip.duration = float(info.get("duration") or 0.0)
                clip.fps = float(info.get("fps") or 30.0) or 30.0
                if not clip.width or not clip.height or clip.duration <= 0:
                    raise ImportError("The selected file is not a supported video", "format")
                start, end = self._clip_range(clip, project.manual)
                total_seconds += max(0.1, end - start)
            if total_seconds <= 0:
                raise ImportError("The selected clips are empty", "empty")
            required = int(total_seconds * max(1, project.width) * max(1, project.height)
                           * 3) + 128 * 1024 * 1024
            if not free_space_ok(required):
                raise ImportError("Not enough free disk space", "disk")

            ffmpeg = ffmpeg_executable()
            if not ffmpeg:
                raise ImportError("FFmpeg is not available", "ffmpeg")
            fps = max(1, min(60, int(project.fps or 30)))
            width = max(2, int(project.width or 1920) // 2 * 2)
            height = max(2, int(project.height or 1080) // 2 * 2)
            self.phase.emit("Preparing clips…")

            normalized: list[str] = []
            done_seconds = 0.0
            for index, clip in enumerate(clips):
                if self._cancel.is_set():
                    raise ImportCancelled("cancelled")
                start, end = self._clip_range(clip, project.manual)
                duration = max(0.1, end - start)
                self.phase.emit("Preparing clips…")
                target = temp_dir / f"clip_{index:03d}.mp4"

                def on_progress(percent: int, base: float = done_seconds,
                                length: float = duration) -> None:
                    overall = (base + length * max(0, min(100, percent)) / 100.0) / total_seconds
                    self.progress.emit(int(overall * 100), "Merging clips…")

                self._render_segment(ffmpeg, clip, start, end, width, height, fps,
                                     target, on_progress)
                normalized.append(str(target))
                done_seconds += duration
                self.progress.emit(int(done_seconds / total_seconds * 88), "Merging clips…")

            if self._cancel.is_set():
                raise ImportCancelled("cancelled")
            self.phase.emit("Joining the merged video…")
            self.progress.emit(90, "Joining the merged video…")
            output = self._concat(ffmpeg, normalized, temp_dir, project, width, height, fps)
            if self._cancel.is_set():
                raise ImportCancelled("cancelled")

            self.phase.emit("Adding to library…")
            self.progress.emit(96, "Adding to library…")
            info = probe_video(output)
            duration = float(info.get("duration") or total_seconds)
            thumb = make_thumbnail(
                output, str(paths.THUMBNAILS_DIR / f"merged_{int(time.time())}.jpg"),
                position=min(1.0, duration / 2))
            title = safe_filename(project.title or f"Merged video {time.strftime('%H-%M')}",
                                  "Merged video")
            imported_at = now_iso()
            digest = hashlib.sha1(
                ("|".join(f"{clip.path}:{clip.start_frame}:{clip.end_frame}" for clip in clips)
                 + str(time.time())).encode("utf-8")).hexdigest()[:16]
            item = MediaItem(
                title=title,
                source="merged",
                source_id=f"merge_{digest}",
                file_path=output,
                original_path=output,
                page_url="",
                thumb_path=thumb or "",
                width=int(info.get("width") or width),
                height=int(info.get("height") or height),
                duration=duration,
                format="MP4",
                size_bytes=os.path.getsize(output),
                imported_at=imported_at,
                aspect=aspect_ratio(width, height),
                added_at=imported_at,
                meta={
                    "merged": True,
                    "fps": float(info.get("fps") or fps),
                    "aspect": aspect_ratio(width, height),
                    "imported_at": imported_at,
                    "original_path": output,
                    "clips": [
                        {"path": clip.path, "start_frame": clip.start_frame,
                         "end_frame": clip.end_frame, "fps": clip.fps}
                        for clip in clips
                    ],
                    "fit": "cover",
                },
            )
            media_id = self.db.upsert_media(item)
            self.library.changed.emit()
            self.progress.emit(100, "Done")
            log.info("merged %d clips into media #%s: %s", len(clips), media_id, output)
            self.finished.emit(int(media_id))
        except ImportCancelled:
            log.info("merge cancelled")
            self.cancelled.emit()
        except ImportError as error:
            log.warning("merge error: %s (%s)", error.message, error.detail)
            self.failed.emit(error.message)
        except Exception as error:  # noqa: BLE001
            log.exception("merge failed")
            self.failed.emit("Could not merge the videos")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            with self._lock:
                self._busy = False

    @staticmethod
    def _clip_range(clip: MergeClip, manual: bool) -> tuple[float, float]:
        fps = clip.fps or 30.0
        total_frames = max(1, int(round(clip.duration * fps)))
        if not manual:
            return 0.0, clip.duration
        start_frame = max(0, min(int(clip.start_frame or 0), total_frames - 1))
        end_frame = int(clip.end_frame or 0)
        if end_frame <= 0:
            end_frame = total_frames
        end_frame = max(start_frame + 1, min(end_frame, total_frames))
        return start_frame / fps, end_frame / fps

    def _render_segment(self, ffmpeg: str, clip: MergeClip, start: float, end: float,
                        width: int, height: int, fps: int, target: Path,
                        progress) -> None:
        duration = max(0.1, end - start)
        has_audio = has_audio_track(clip.path)
        filter_graph = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps},setpts=PTS-STARTPTS[v]")
        command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-nostats",
                   "-progress", "pipe:1",
                   "-ss", f"{start:.3f}", "-i", clip.path]
        if not has_audio:
            command += ["-f", "lavfi", "-i",
                        "anullsrc=channel_layout=stereo:sample_rate=48000"]
        command += ["-t", f"{duration:.3f}",
                    "-filter_complex", filter_graph, "-map", "[v]"]
        if has_audio:
            command += ["-map", "0:a:0", "-af", "apad", "-c:a", "aac",
                        "-ar", "48000", "-ac", "2"]
        else:
            command += ["-map", "1:a:0", "-c:a", "aac", "-ar", "48000", "-ac", "2"]
        command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-r", str(fps),
                    "-movflags", "+faststart", str(target)]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True,
                                   creationflags=creationflags)
        assert process.stdout is not None
        for line in process.stdout:
            if self._cancel.is_set():
                process.terminate()
                raise ImportCancelled("cancelled")
            if line.startswith("out_time_us="):
                try:
                    seconds = int(line.split("=", 1)[1]) / 1_000_000.0
                except (TypeError, ValueError):
                    continue
                progress(int(max(0, min(100, seconds / duration * 100))))
        process.wait(timeout=30)
        errors = process.stderr.read() if process.stderr is not None else ""
        if self._cancel.is_set():
            raise ImportCancelled("cancelled")
        if process.returncode != 0 or not target.exists():
            raise ImportError("Could not prepare the merged video", "merge",
                              (errors or "ffmpeg failed").strip()[:400])
        if target.stat().st_size <= 0:
            raise ImportError("The prepared video is empty", "merge")

    def _concat(self, ffmpeg: str, files: list[str], temp_dir: Path,
                project: MergeProject, width: int, height: int, fps: int) -> str:
        list_path = temp_dir / "list.txt"
        lines = []
        for path in files:
            escaped = path.replace("'", "'\\''")
            lines.append(f"file '{escaped}'\n")
        list_path.write_text("".join(lines), encoding="utf-8")
        library_dir = Path(self.settings.get("storage.library_dir",
                                             str(paths.DEFAULT_LIBRARY_DIR)))
        library_dir.mkdir(parents=True, exist_ok=True)
        base = safe_filename(project.title or "Merged video", "Merged video")
        target = library_dir / f"{base}_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
        counter = 1
        while target.exists():
            target = library_dir / f"{base}_{time.strftime('%Y%m%d_%H%M%S')}_{counter}.mp4"
            counter += 1
        command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                   "-f", "concat", "-safe", "0", "-i", str(list_path),
                   "-c", "copy", "-movflags", "+faststart", str(target)]
        process = subprocess.run(command, capture_output=True, text=True,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if process.returncode != 0 or not target.exists():
            raise ImportError("Could not join the prepared clips", "merge",
                              (process.stderr or "ffmpeg failed").strip()[:400])
        return str(target)
