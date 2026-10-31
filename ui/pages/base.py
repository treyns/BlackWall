"""Base class for application pages."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ui.theme import current_theme


class BasePage(QWidget):
    PAGE_KEY = "page"
    TITLE = "Page"
    SUBTITLE = ""

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PageRoot")
        self.ctx = ctx
        self.theme = current_theme()
        self.root = QVBoxLayout(self)
        margin = self.theme.px(28)
        self.root.setContentsMargins(margin, self.theme.px(18), margin, margin)
        self.root.setSpacing(self.theme.px(18))

    def on_show(self) -> None:  # noqa: B027 - optional hook
        pass

    def on_hide(self) -> None:  # noqa: B027 - optional hook
        pass

    def scroll_to_top(self) -> None:
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "verticalScrollBar"):
                parent.verticalScrollBar().setValue(0)
                return
            parent = parent.parent()
