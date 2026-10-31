"""Tiny translation layer.

UI strings are written in English directly in the code and wrapped into
``tr("...")``.  A translation file ``assets/i18n/<lang>.json`` maps the English
source string to the translated one.  Missing keys fall back to the source, so
the app always works even with an incomplete translation.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from config import paths

_LOCK = threading.RLock()


class Translator:
    def __init__(self, language: str = "ru", folder: Path | None = None) -> None:
        self._folder = Path(folder) if folder else paths.I18N_DIR
        self._language = language
        self._strings: dict[str, str] = {}
        self._fallback: dict[str, str] = {}
        self.load()

    # ------------------------------------------------------------------ state
    @property
    def language(self) -> str:
        with _LOCK:
            return self._language

    def available_languages(self) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        if self._folder.exists():
            for file in sorted(self._folder.glob("*.json")):
                code = file.stem
                label = {"en": "English", "ru": "Русский"}.get(code, code.upper())
                found.append((code, label))
        if not found:
            found = [("en", "English"), ("ru", "Русский")]
        return found

    def load(self) -> None:
        with _LOCK:
            self._strings = self._read_file(self._language)
            if self._language != "en":
                self._fallback = self._read_file("en")
            else:
                self._fallback = {}

    def _read_file(self, code: str) -> dict[str, str]:
        file = self._folder / f"{code}.json"
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def set_language(self, language: str) -> None:
        with _LOCK:
            self._language = language or "en"
        self.load()

    # ------------------------------------------------------------------- look
    def translate(self, text: str, **kwargs) -> str:
        with _LOCK:
            translated = self._strings.get(text)
            if translated is None:
                translated = self._fallback.get(text, text)
        if kwargs:
            try:
                return translated.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                return translated
        return translated

    def __call__(self, text: str, **kwargs) -> str:
        return self.translate(text, **kwargs)


translator = Translator()
tr = translator.translate


def set_language(language: str) -> None:
    translator.set_language(language)


def current_language() -> str:
    return translator.language
