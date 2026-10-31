import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config.settings import DEFAULTS, Settings


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "settings.json")
        self.settings = Settings(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_defaults(self) -> None:
        self.assertEqual(self.settings.get("general.language"), "ru")
        self.assertEqual(self.settings.get("performance.fps_cap"), 30)
        self.assertEqual(self.settings.get("performance.mode"), "balanced")
        self.assertFalse(self.settings.get("general.run_at_startup"))

    def test_set_get_and_persist(self) -> None:
        self.settings.set("performance.fps_cap", 15)
        self.settings.set("appearance.accent", "violet")
        self.settings.set("monitors.assignments", {"m1": {"file_path": "x.mp4"}})
        again = Settings(self.path)
        self.assertEqual(again.get("performance.fps_cap"), 15)
        self.assertEqual(again.get("appearance.accent"), "violet")
        self.assertEqual(again.get("monitors.assignments")["m1"]["file_path"], "x.mp4")

    def test_listener(self) -> None:
        changes = []
        self.settings.add_listener(changes.append)
        self.settings.set("general.check_updates", True)
        self.assertEqual(changes[-1], "general.check_updates")
        self.settings.remove_listener(changes.append)

    def test_api_key_helpers(self) -> None:
        self.settings.set("providers.pixabay_key", "  abc  ")
        self.assertEqual(self.settings.api_key("pixabay"), "abc")
        self.assertEqual(self.settings.api_key("pexels"), "")

    def test_defaults_are_not_mutated(self) -> None:
        self.settings.set("general.language", "en")
        self.assertEqual(DEFAULTS["general"]["language"], "ru")

    def test_unknown_key_returns_default(self) -> None:
        self.assertEqual(self.settings.get("nope.nothing", "fallback"), "fallback")


if __name__ == "__main__":
    unittest.main()
