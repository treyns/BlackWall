import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.i18n import Translator
from core.models import Assignment, MediaItem, SearchResult


class ModelTests(unittest.TestCase):
    def test_search_result_roundtrip(self) -> None:
        result = SearchResult(
            provider="pixabay", source_id="42", title="Nebula", width=1920, height=1080,
            duration=10, thumbnail_url="https://x/thumb.jpg",
            preview_url="https://x/preview.mp4", video_url="https://x/video.mp4",
            page_url="https://pixabay.com/v/42", author="Author", tags=["space"],
        )
        restored = SearchResult.from_dict(result.to_dict())
        self.assertEqual(restored.uid, "pixabay:42")
        self.assertEqual(restored.resolution, "1920 × 1080")
        self.assertEqual(restored.duration_text, "0:10")
        self.assertEqual(restored.tags, ["space"])

    def test_search_result_to_media(self) -> None:
        result = SearchResult(provider="pexels", source_id="7", title="Sea",
                              width=1280, height=720, duration=12,
                              download_url="https://x/v.mp4")
        media = result.to_media()
        self.assertEqual(media.source, "pexels")
        self.assertFalse(media.is_local)
        self.assertEqual(media.meta["download_url"], "https://x/v.mp4")

    def test_media_from_row(self) -> None:
        row = {
            "id": 5, "title": "Wall", "source": "local", "source_id": "abc",
            "file_path": "C:/x.mp4", "page_url": None, "thumb_path": None,
            "width": 1920, "height": 1080, "duration": 9.5, "format": "MP4",
            "size_bytes": 100, "added_at": "2026-01-01", "last_used_at": "",
            "is_favorite": 1, "favorite_at": "2026-01-02", "meta": '{"tags": ["a"]}',
        }
        media = MediaItem.from_row(row)
        self.assertEqual(media.id, 5)
        self.assertTrue(media.is_favorite)
        self.assertEqual(media.meta["tags"], ["a"])
        self.assertEqual(media.resolution, "1920 × 1080")

    def test_assignment_roundtrip(self) -> None:
        assignment = Assignment(monitor_key="m1", media_id=3, file_path="C:/v.mp4",
                                kind="video", fit="contain", muted=False, volume=50,
                                title="Video")
        restored = Assignment.from_dict("m1", assignment.to_dict())
        self.assertEqual(restored.fit, "contain")
        self.assertFalse(restored.muted)
        self.assertEqual(restored.volume, 50)


class I18nTests(unittest.TestCase):
    def test_fallback_and_translation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "ru.json"), "w", encoding="utf-8") as handle:
                json.dump({"Hello": "Привет"}, handle, ensure_ascii=False)
            translator = Translator("ru", folder=folder)
            self.assertEqual(translator("Hello"), "Привет")
            self.assertEqual(translator("Unknown string"), "Unknown string")
            self.assertEqual(translator("Hello"), "Привет")

    def test_formatting(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            translator = Translator("ru", folder=folder)
            self.assertEqual(translator("Count: {n}", n=3), "Count: 3")

    def test_language_switch(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "ru.json"), "w", encoding="utf-8") as handle:
                json.dump({"Open": "Открыть"}, handle, ensure_ascii=False)
            translator = Translator("en", folder=folder)
            self.assertEqual(translator("Open"), "Open")
            translator.set_language("ru")
            self.assertEqual(translator("Open"), "Открыть")


if __name__ == "__main__":
    unittest.main()
