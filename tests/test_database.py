import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.database import Database
from core.models import DownloadTask, MediaItem


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "test.db"))
        self.video = os.path.join(self.tmp.name, "wallpaper.mp4")
        with open(self.video, "wb") as handle:
            handle.write(b"0" * 1024)

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_add_local_file_and_list(self) -> None:
        media_id = self.db.add_local_file(self.video, title="Test Wallpaper", width=1920,
                                          height=1080, duration=12.5, fmt="MP4")
        self.assertGreater(media_id, 0)
        items = self.db.list_library()
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.title, "Test Wallpaper")
        self.assertEqual(item.width, 1920)
        self.assertEqual(item.duration, 12.5)
        self.assertEqual(item.kind, "video")

    def test_duplicate_import_updates_instead_of_duplicating(self) -> None:
        first = self.db.add_local_file(self.video, title="A")
        second = self.db.add_local_file(self.video, title="B")
        self.assertEqual(first, second)
        self.assertEqual(len(self.db.list_library()), 1)
        self.assertEqual(self.db.get_media(first).title, "B")

    def test_favorites_and_stats(self) -> None:
        media_id = self.db.add_local_file(self.video, title="Fav")
        self.assertTrue(self.db.toggle_favorite(media_id))
        favorites = self.db.list_favorites()
        self.assertEqual(len(favorites), 1)
        self.assertTrue(favorites[0].is_favorite)
        stats = self.db.stats()
        self.assertEqual(stats["library"], 1)
        self.assertEqual(stats["favorites"], 1)
        self.db.set_favorite(media_id, False)
        self.assertEqual(len(self.db.list_favorites()), 0)

    def test_search_and_sort(self) -> None:
        self.db.add_local_file(self.video, title="Ocean Waves")
        other = os.path.join(self.tmp.name, "forest.jpg")
        with open(other, "wb") as handle:
            handle.write(b"1" * 512)
        self.db.add_local_file(other, title="Forest Night")
        self.assertEqual(len(self.db.list_library(search="ocean")), 1)
        self.assertEqual(len(self.db.list_library(search="night")), 1)
        self.assertEqual(len(self.db.list_library(kind="image")), 1)
        titles = [item.title for item in self.db.list_library(sort="title")]
        self.assertEqual(titles, ["Forest Night", "Ocean Waves"])

    def test_remote_media_and_favorites(self) -> None:
        item = MediaItem(
            title="Remote Nebula",
            source="pixabay",
            source_id="12345",
            thumb_path="https://example.com/thumb.jpg",
            width=1920,
            height=1080,
            meta={"download_url": "https://example.com/video.mp4", "tags": ["space"]},
        )
        media_id = self.db.upsert_media(item)
        self.assertIsNotNone(media_id)
        fetched = self.db.get_by_source("pixabay", "12345")
        self.assertIsNotNone(fetched)
        self.assertFalse(fetched.is_local)
        self.assertEqual(len(self.db.list_remote()), 1)
        self.assertEqual(len(self.db.list_library()), 0)
        self.db.set_favorite(media_id, True)
        self.assertEqual(len(self.db.list_favorites()), 1)
        self.assertEqual(self.db.stats()["remote_favorites"], 1)

    def test_downloads_crud(self) -> None:
        task = DownloadTask(title="Video", url="https://example.com/v.mp4",
                            dest_path=os.path.join(self.tmp.name, "v.mp4"),
                            status="queued", source="pixabay")
        download_id = self.db.add_download(task)
        self.assertGreater(download_id, 0)
        self.assertEqual(len(self.db.list_downloads()), 1)
        task.status = "completed"
        task.downloaded_bytes = 100
        self.db.update_download(task)
        self.assertEqual(self.db.get_download(download_id).status, "completed")
        self.db.delete_download(download_id)
        self.assertEqual(len(self.db.list_downloads()), 0)

    def test_recent_and_touch(self) -> None:
        media_id = self.db.add_local_file(self.video, title="Recent")
        self.assertEqual(len(self.db.recent()), 0)
        self.db.touch_used(media_id)
        self.assertEqual(len(self.db.recent()), 1)


if __name__ == "__main__":
    unittest.main()
