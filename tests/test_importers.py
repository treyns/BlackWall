"""Unit tests for link detection, import metadata helpers and DB import fields."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config.constants import FIT_MODE_ORDER, FIT_MODES
from core.database import Database
from core.models import Assignment, MediaItem
from importers.base import detect_link, friendly_download_error
from importers.processing import aspect_ratio, needs_optimization, target_dimensions


class LinkDetectionTests(unittest.TestCase):
    def test_youtube_variants(self) -> None:
        cases = {
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ": "dQw4w9WgXcQ",
            "youtu.be/jNQXAC9IVRw?t=5": "jNQXAC9IVRw",
            "https://youtube.com/shorts/abcDEF12345": "abcDEF12345",
            "https://m.youtube.com/watch?v=jNQXAC9IVRw": "jNQXAC9IVRw",
        }
        for text, expected in cases.items():
            link = detect_link(text)
            self.assertIsNotNone(link, text)
            self.assertEqual(link.source, "youtube")
            self.assertEqual(link.video_id, expected)

    def test_tiktok_variants(self) -> None:
        for text in ("https://www.tiktok.com/@user/video/6718335390845095173",
                     "https://m.tiktok.com/v/6718335390845095173.html",
                     "https://vm.tiktok.com/ZMabc123/",
                     "https://vt.tiktok.com/ZSabc123/"):
            link = detect_link(text)
            self.assertIsNotNone(link, text)
            self.assertEqual(link.source, "tiktok")

    def test_pinterest_variants(self) -> None:
        cases = {
            "https://www.pinterest.com/pin/351912467391055/": "351912467391055",
            "https://ru.pinterest.com/pin/351912467391055/": "351912467391055",
            "https://pinterest.co.uk/pin/351912467391055/": "351912467391055",
            "https://pin.it/AbCdEf123": "AbCdEf123",
        }
        for text, expected in cases.items():
            link = detect_link(text)
            self.assertIsNotNone(link, text)
            self.assertEqual(link.source, "pinterest")
            self.assertEqual(link.video_id, expected)

    def test_pasted_text_with_link(self) -> None:
        link = detect_link("look at this https://youtu.be/dQw4w9WgXcQ cool")
        self.assertIsNotNone(link)
        self.assertEqual(link.video_id, "dQw4w9WgXcQ")

    def test_quality_tiers_include_4k_and_2k(self) -> None:
        from config.constants import VIDEO_QUALITY_OPTIONS, VIDEO_QUALITY_WIDTHS
        keys = [key for key, _label in VIDEO_QUALITY_OPTIONS]
        self.assertIn("4320p", keys)
        self.assertIn("2160p", keys)
        self.assertIn("1440p", keys)
        self.assertEqual(VIDEO_QUALITY_WIDTHS["2160p"], 3840)
        self.assertEqual(VIDEO_QUALITY_WIDTHS["1440p"], 2560)

    def test_not_a_link(self) -> None:
        self.assertIsNone(detect_link("https://example.com/video/123"))
        self.assertIsNone(detect_link(""))


class ProcessingHelpersTests(unittest.TestCase):
    def test_aspect_ratio(self) -> None:
        self.assertEqual(aspect_ratio(1920, 1080), "16:9")
        self.assertEqual(aspect_ratio(1080, 1920), "9:16")
        self.assertEqual(aspect_ratio(1280, 1024), "5:4")
        self.assertEqual(aspect_ratio(0, 0), "")

    def test_target_dimensions_do_not_upscale(self) -> None:
        class M:
            def __init__(self, width, height):
                self.width, self.height = width, height

        monitors = [M(1920, 1080), M(1280, 1024)]
        self.assertEqual(target_dimensions(3840, 2160, monitors), (1920, 1080))
        self.assertEqual(target_dimensions(720, 1280, monitors), (720, 1280))
        self.assertEqual(target_dimensions(1920, 1080, monitors), (1920, 1080))

    def test_needs_optimization(self) -> None:
        self.assertTrue(needs_optimization(
            {"width": 3840, "height": 2160, "fps": 30, "compatible": True}, 1920, 1080))
        self.assertFalse(needs_optimization(
            {"width": 1920, "height": 1080, "fps": 30, "compatible": True}, 1920, 1080))
        self.assertTrue(needs_optimization(
            {"width": 1920, "height": 1080, "fps": 120, "compatible": True}, 1920, 1080))


class ErrorMappingTests(unittest.TestCase):
    def test_private_and_drm(self) -> None:
        self.assertEqual(friendly_download_error(Exception("Private video")).code, "private")
        self.assertEqual(friendly_download_error(Exception("DRM protected")).code, "drm")
        self.assertEqual(friendly_download_error(Exception("Sign in to confirm")).code, "login")
        self.assertEqual(friendly_download_error(Exception("HTTP Error 403")).code, "forbidden")
        self.assertEqual(friendly_download_error(Exception("Unsupported URL")).code, "unsupported")


class ImportDatabaseTests(unittest.TestCase):
    def test_import_fields_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            db = Database(os.path.join(folder, "media.db"))
            item = MediaItem(
                title="Test", source="youtube", source_id="abc123",
                file_path=os.path.join(folder, "a.mp4"),
                original_path=os.path.join(folder, "a.mp4"),
                optimized_path=os.path.join(folder, "a_opt.mp4"),
                imported_at="2026-01-01 12:00:00", author="author", aspect="9:16")
            media_id = db.upsert_media(item)
            got = db.get_media(media_id)
            self.assertEqual(got.original_path, item.original_path)
            self.assertEqual(got.optimized_path, item.optimized_path)
            self.assertEqual(got.imported_at, item.imported_at)
            self.assertEqual(got.author, "author")
            self.assertEqual(got.aspect, "9:16")
            db.update_import_info(media_id, optimized_path=os.path.join(folder, "b.mp4"))
            self.assertEqual(db.get_media(media_id).optimized_path,
                             os.path.join(folder, "b.mp4"))
            db.close()


class DisplayModeTests(unittest.TestCase):
    def test_blur_mode_is_available(self) -> None:
        self.assertIn("blur", FIT_MODES)
        self.assertEqual(FIT_MODE_ORDER[0], "cover")
        self.assertEqual(len(FIT_MODE_ORDER), 4)

    def test_assignment_quality_and_fps_roundtrip(self) -> None:
        assignment = Assignment(monitor_key="m", media_id=1, file_path="x.mp4",
                                quality="720p", fps_cap=30, paused=True,
                                muted=False, volume=55)
        restored = Assignment.from_dict("m", assignment.to_dict())
        self.assertEqual(restored.quality, "720p")
        self.assertEqual(restored.fps_cap, 30)
        self.assertTrue(restored.paused)
        self.assertFalse(restored.muted)
        self.assertEqual(restored.volume, 55)
        legacy = Assignment.from_dict("m", {"fit": "cover"})
        self.assertEqual(legacy.quality, "original")
        self.assertEqual(legacy.fps_cap, 0)
        self.assertFalse(legacy.paused)


if __name__ == "__main__":
    unittest.main()
