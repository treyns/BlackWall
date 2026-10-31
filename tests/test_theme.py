"""Tests for the Aurora/Classic theme system and settings migration."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config.constants import ACCENTS, ACCENTS_BY_THEME, AURORA_ACCENTS
from config.settings import Settings
from ui.theme import Theme, normalize_appearance


class ThemePaletteTests(unittest.TestCase):
    def test_aurora_palette(self) -> None:
        theme = Theme(design="aurora", accent="purple")
        self.assertEqual(theme.color("bg"), "#000000")
        self.assertEqual(theme.color("card"), "#141414")
        self.assertEqual(theme.color("accent"), "#8B35FF")
        self.assertEqual(theme.color("text"), "#FFFFFF")

    def test_classic_palette_is_original(self) -> None:
        theme = Theme(design="classic", accent="yellow")
        self.assertEqual(theme.color("bg"), "#101113")
        self.assertEqual(theme.color("card"), "#1C1E22")
        self.assertEqual(theme.color("accent"), "#F2C72E")

    def test_accent_falls_back_per_theme(self) -> None:
        self.assertEqual(Theme(design="classic", accent="purple").color("accent"),
                         ACCENTS["yellow"]["accent"])
        self.assertEqual(Theme(design="aurora", accent="yellow").color("accent"),
                         AURORA_ACCENTS["purple"]["accent"])
        self.assertIn("cyan", ACCENTS_BY_THEME["aurora"])
        self.assertIn("violet", ACCENTS_BY_THEME["classic"])


class ThemeMigrationTests(unittest.TestCase):
    def test_old_dark_theme_migrates_to_aurora(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "settings.json")
            settings = Settings(path)
            settings.set("appearance.theme", "dark")
            settings.set("appearance.accent", "yellow")
            design, accent = normalize_appearance(settings)
            self.assertEqual(design, "aurora")
            self.assertEqual(accent, "purple")
            self.assertEqual(settings.get("appearance.theme"), "aurora")
            self.assertEqual(settings.get("appearance.accent"), "purple")
            self.assertEqual(settings.get("appearance.classic_accent"), "yellow")
            with open(path, encoding="utf-8") as stream:
                saved = json.load(stream)
            self.assertEqual(saved["appearance"]["theme"], "aurora")
            self.assertEqual(saved["appearance"]["accent"], "purple")

    def test_explicit_classic_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "settings.json")
            settings = Settings(path)
            settings.set("appearance.theme", "classic")
            settings.set("appearance.accent", "violet")
            design, accent = normalize_appearance(settings)
            self.assertEqual(design, "classic")
            self.assertEqual(accent, "violet")
            self.assertEqual(settings.get("appearance.theme"), "classic")


if __name__ == "__main__":
    unittest.main()
