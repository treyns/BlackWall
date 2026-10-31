import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import utils
from core.models import media_kind

TEST_VIDEO = os.path.join(ROOT, "scripts", "dev", "test_1080p30.mp4")


class UtilsTests(unittest.TestCase):
    def test_human_size(self) -> None:
        self.assertEqual(utils.human_size(0), "—")
        self.assertEqual(utils.human_size(512), "512 B")
        self.assertEqual(utils.human_size(1024 * 1024 * 2), "2.0 MB")
        self.assertEqual(utils.human_size(1024 ** 3), "1.0 GB")

    def test_human_duration(self) -> None:
        self.assertEqual(utils.human_duration(0), "—")
        self.assertEqual(utils.human_duration(8), "0:08")
        self.assertEqual(utils.human_duration(125), "2:05")
        self.assertEqual(utils.human_duration(3725), "1:02:05")

    def test_safe_filename(self) -> None:
        cleaned = utils.safe_filename('a/b:c*?"<>|')
        self.assertFalse(any(char in cleaned for char in '/:*?"<>|'))
        self.assertTrue(cleaned.startswith("a_b_c"))
        self.assertEqual(utils.safe_filename("   "), "wallpaper")
        self.assertTrue(len(utils.safe_filename("x" * 500)) <= 120)

    def test_media_kind(self) -> None:
        self.assertEqual(media_kind("clip.mp4"), "video")
        self.assertEqual(media_kind(".webm"), "video")
        self.assertEqual(media_kind("loop.gif"), "animation")
        self.assertEqual(media_kind("loop.webp"), "animation")
        self.assertEqual(media_kind("photo.jpg"), "image")
        self.assertEqual(media_kind(""), "image")

    def test_probe_media_video(self) -> None:
        if not os.path.exists(TEST_VIDEO):
            self.skipTest("test video not generated")
        info = utils.probe_media(TEST_VIDEO)
        self.assertEqual(info["kind"], "video")
        self.assertEqual(info["width"], 1920)
        self.assertEqual(info["height"], 1080)
        self.assertAlmostEqual(info["duration"], 8.0, delta=0.5)
        self.assertGreater(info["fps"], 25)

    def test_probe_media_missing_file(self) -> None:
        info = utils.probe_media(os.path.join(ROOT, "does-not-exist.mp4"))
        self.assertEqual(info["width"], 0)
        self.assertEqual(info["kind"], "video")

    def test_thumbnail_generation(self) -> None:
        if not os.path.exists(TEST_VIDEO):
            self.skipTest("test video not generated")
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "thumb.jpg")
            self.assertTrue(utils.thumbnail_for(TEST_VIDEO, target, width=320))
            self.assertTrue(os.path.exists(target))
            self.assertGreater(os.path.getsize(target), 500)


if __name__ == "__main__":
    unittest.main()
