"""Wallpaper cards used by Home, Library, Favourites and Discover."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.i18n import tr
from core.models import MediaItem, SearchResult
from core.utils import human_duration
from ui import icons
from ui.components.thumbs import ThumbnailWidget
from ui.components.widgets import Badge, Divider, h3, text_label
from ui.theme import current_theme


class _BaseCard(QFrame):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", False)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if child is None or not isinstance(child, QPushButton):
                self.clicked.emit()
        super().mouseReleaseEvent(event)


def _small_button(text: str, icon_name: str | None = None, primary: bool = False) -> QPushButton:
    theme = current_theme()
    button = QPushButton(text)
    button.setObjectName("Primary" if primary else "Outline")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if icon_name:
        button.setIcon(icons.icon(icon_name, theme.color("accent_text" if primary else "text"),
                                  theme.px(15)))
    return button


class WallpaperCard(_BaseCard):
    """Card for a library / favourite wallpaper."""

    install_requested = Signal(int)
    favorite_toggled = Signal(int)
    menu_requested = Signal(int, QPoint)

    CARD_WIDTH = 300
    THUMB_HEIGHT = 168

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self.setFixedWidth(theme.px(self.CARD_WIDTH))
        self.item: MediaItem | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.thumb = ThumbnailWidget(self.CARD_WIDTH, self.THUMB_HEIGHT)
        layout.addWidget(self.thumb)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(theme.px(14), theme.px(12), theme.px(14), theme.px(12))
        body_layout.setSpacing(theme.px(6))

        title_row = QHBoxLayout()
        title_row.setSpacing(theme.px(6))
        self.title_label = h3("")
        self.title_label.setMinimumWidth(10)
        title_row.addWidget(self.title_label, 1)
        self.favorite_button = QPushButton()
        self.favorite_button.setObjectName("IconButton")
        self.favorite_button.setFixedSize(theme.px(26), theme.px(26))
        self.favorite_button.setCursor(Qt.CursorShape.PointingHandCursor)
        title_row.addWidget(self.favorite_button)
        body_layout.addLayout(title_row)

        self.meta_label = text_label("", "CardMeta")
        body_layout.addWidget(self.meta_label)

        self.badge_row = QHBoxLayout()
        self.badge_row.setSpacing(theme.px(6))
        self.kind_badge = Badge("", accent=False)
        self.source_badge = Badge("", accent=True)
        self.badge_row.addWidget(self.kind_badge)
        self.badge_row.addWidget(self.source_badge)
        self.badge_row.addStretch(1)
        body_layout.addLayout(self.badge_row)

        divider = Divider()
        body_layout.addWidget(divider)

        action_row = QHBoxLayout()
        action_row.setSpacing(theme.px(6))
        self.install_button = _small_button(tr("Install"), "play", True)
        self.install_button.clicked.connect(self._on_install)
        action_row.addWidget(self.install_button, 1)
        self.more_button = QPushButton()
        self.more_button.setObjectName("IconButton")
        self.more_button.setIcon(icons.icon("settings", theme.color("text_dim"), theme.px(17)))
        self.more_button.setFixedSize(theme.px(32), theme.px(30))
        self.more_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more_button.clicked.connect(self._on_more)
        action_row.addWidget(self.more_button)
        body_layout.addLayout(action_row)

        layout.addWidget(body)
        self._refresh_favorite_icon()

    # ---------------------------------------------------------------- binding
    def set_item(self, item: MediaItem) -> None:
        self.item = item
        self.thumb.set_source(item.file_path or item.thumb_path or "", key=f"media:{item.id}")
        self.title_label.setText(item.title or tr("Untitled"))
        self.title_label.setToolTip(item.title)
        parts = [item.resolution]
        if item.format:
            parts.append(str(item.format).upper())
        if item.duration:
            parts.append(human_duration(item.duration))
        self.meta_label.setText(" · ".join(part for part in parts if part and part != "—"))
        kind_labels = {
            "video": tr("VIDEO"),
            "animation": tr("ANIMATED"),
            "image": tr("IMAGE"),
        }
        self.kind_badge.setText(kind_labels.get(item.kind, tr("FILE")))
        self.source_badge.setText(item.source.upper() if item.source != "local" else tr("LOCAL"))
        self.install_button.setText(tr("Install") if item.is_local else tr("Download"))
        self.install_button.setEnabled(True)
        self._refresh_favorite_icon()

    def set_installed(self, installed: bool) -> None:
        self.install_button.setText(tr("Install") if installed else tr("Download"))

    def _refresh_favorite_icon(self) -> None:
        theme = current_theme()
        favorite = bool(self.item and self.item.is_favorite)
        self.favorite_button.setIcon(icons.icon(
            "star-filled" if favorite else "star",
            theme.color("accent") if favorite else theme.color("text_dim"),
            theme.px(17),
        ))
        self.favorite_button.setToolTip(tr("Remove from favorites") if favorite else tr("Add to favorites"))

    # ---------------------------------------------------------------- actions
    def _on_install(self) -> None:
        if self.item and self.item.id is not None:
            self.install_requested.emit(int(self.item.id))

    def _on_more(self) -> None:
        if self.item and self.item.id is not None:
            self.menu_requested.emit(int(self.item.id), self.more_button.mapToGlobal(
                QPoint(0, self.more_button.height())))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.RightButton:
            if self.item and self.item.id is not None:
                self.menu_requested.emit(int(self.item.id), event.globalPosition().toPoint())
            return
        super().mouseReleaseEvent(event)


class ResultCard(_BaseCard):
    """Card for a remote search result."""

    preview_requested = Signal(object)
    download_requested = Signal(object)
    favorite_requested = Signal(object)

    CARD_WIDTH = 288
    THUMB_HEIGHT = 162

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self.setFixedWidth(theme.px(self.CARD_WIDTH))
        self.result: SearchResult | None = None
        self._favorite = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        thumb_holder = QWidget()
        thumb_holder.setFixedHeight(theme.px(self.THUMB_HEIGHT))
        self.thumb = ThumbnailWidget(self.CARD_WIDTH, self.THUMB_HEIGHT, thumb_holder)
        self.thumb.move(0, 0)
        self.duration_badge = QLabel("", thumb_holder)
        self.duration_badge.setObjectName("BadgeDim")
        self.duration_badge.setStyleSheet(
            f"background-color: rgba(16,17,19,200); color: {theme.color('text')};"
            "border-radius: 8px; padding: 1px 7px; font-size: 11px;")
        layout.addWidget(thumb_holder)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(theme.px(14), theme.px(10), theme.px(14), theme.px(12))
        body_layout.setSpacing(theme.px(5))

        self.title_label = h3("")
        body_layout.addWidget(self.title_label)
        self.meta_label = text_label("", "CardMeta")
        body_layout.addWidget(self.meta_label)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(theme.px(6))
        self.provider_badge = Badge("", accent=True)
        self.resolution_badge = Badge("", accent=False)
        badge_row.addWidget(self.provider_badge)
        badge_row.addWidget(self.resolution_badge)
        badge_row.addStretch(1)
        body_layout.addLayout(badge_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(theme.px(6))
        preview_button = _small_button(tr("Preview"), "play")
        preview_button.clicked.connect(self._on_preview)
        action_row.addWidget(preview_button, 1)
        download_button = QPushButton()
        download_button.setObjectName("IconButton")
        download_button.setIcon(icons.icon("downloads", theme.color("text_dim"), theme.px(17)))
        download_button.setFixedSize(theme.px(32), theme.px(30))
        download_button.setToolTip(tr("Download"))
        download_button.setCursor(Qt.CursorShape.PointingHandCursor)
        download_button.clicked.connect(self._on_download)
        action_row.addWidget(download_button)
        self.favorite_button = QPushButton()
        self.favorite_button.setObjectName("IconButton")
        self.favorite_button.setFixedSize(theme.px(32), theme.px(30))
        self.favorite_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.favorite_button.clicked.connect(self._on_favorite)
        action_row.addWidget(self.favorite_button)
        body_layout.addLayout(action_row)

        layout.addWidget(body)
        self._refresh_favorite_icon()

    def set_result(self, result: SearchResult, favorite: bool = False) -> None:
        self.result = result
        self._favorite = favorite
        self.thumb.set_source(result.thumbnail_url, key=f"remote:{result.uid}")
        self.title_label.setText(result.title or tr("Untitled"))
        self.title_label.setToolTip(result.title)
        self.meta_label.setText(" · ".join(part for part in (
            result.author or "",
            human_duration(result.duration) if result.duration else "",
        ) if part) or "—")
        self.provider_badge.setText(result.provider.upper())
        self.resolution_badge.setText(result.resolution)
        self.duration_badge.setText(result.duration_text)
        self.duration_badge.adjustSize()
        self.duration_badge.move(
            self.thumb.width() - self.duration_badge.width() - theme_px(8),
            self.thumb.height() - self.duration_badge.height() - theme_px(8))
        self._refresh_favorite_icon()

    def set_favorite(self, value: bool) -> None:
        self._favorite = value
        self._refresh_favorite_icon()

    def _refresh_favorite_icon(self) -> None:
        theme = current_theme()
        self.favorite_button.setIcon(icons.icon(
            "star-filled" if self._favorite else "star",
            theme.color("accent") if self._favorite else theme.color("text_dim"),
            theme.px(17)))
        self.favorite_button.setToolTip(tr("In favorites") if self._favorite else tr("Add to favorites"))

    def _on_preview(self) -> None:
        if self.result:
            self.preview_requested.emit(self.result)

    def _on_download(self) -> None:
        if self.result:
            self.download_requested.emit(self.result)

    def _on_favorite(self) -> None:
        if self.result:
            self.favorite_requested.emit(self.result)


def theme_px(value: float) -> int:
    return current_theme().px(value)


