import os
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtCore import QCoreApplication

from core import utils
from library.lightcopy import LightCopyManager

TEST_VIDEO = os.path.join(ROOT, "scripts", "dev", "test_1080p30.mp4")


class LightCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def _generate(self, manager: LightCopyManager, width: int) -> str:
        result = {}

        def on_ready(source: str, path: str, target_width: int) -> None:
            result["path"] = path
            result["width"] = target_width

        manager.ready.connect(on_ready)
        manager.request(TEST_VIDEO, width)
        deadline = time.time() + 120
        while time.time() < deadline and "path" not in result:
            self.app.processEvents()
            time.sleep(0.05)
        self.assertIn("path", result, "lightweight copy was not generated")
        self.assertEqual(result["width"], width)
        self.assertTrue(os.path.exists(result["path"]))
        self.assertGreater(os.path.getsize(result["path"]), 10_000)
        info = utils.probe_media(result["path"])
        self.assertLessEqual(info["width"], width)
        self.assertGreater(info["width"], 0)
        return result["path"]

    def test_generates_light_copies_for_multiple_qualities(self) -> None:
        if not os.path.exists(TEST_VIDEO):
            self.skipTest("test video is not available")
        try:
            import imageio_ffmpeg  # noqa: F401
        except ImportError:
            self.skipTest("imageio-ffmpeg is not installed")
        with tempfile.TemporaryDirectory() as folder:
            manager = LightCopyManager(folder)
            path_720 = self._generate(manager, 1280)
            self.assertEqual(manager.path_for(TEST_VIDEO, 1280), path_720)
            path_480 = self._generate(manager, 854)
            self.assertNotEqual(path_720, path_480)
            self.assertEqual(manager.path_for(TEST_VIDEO, 854), path_480)
            # cached files are reused, not re-encoded
            manager.request(TEST_VIDEO, 1280)
            self.app.processEvents()
            self.assertFalse(manager.is_pending(TEST_VIDEO, 1280))

    def test_missing_file_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manager = LightCopyManager(folder)
            manager.request(os.path.join(folder, "nope.mp4"), 1280)
            self.assertEqual(manager.pending_count(), 0)


if __name__ == "__main__":
    unittest.main()

