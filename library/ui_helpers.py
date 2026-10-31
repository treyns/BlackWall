"""Shared UI helpers for the Library and Favorites pages.

Small local widgets/menus are kept here (instead of the shared ``ui/components``
files) so the two pages stay self-contained: library cards with real actions,
the install-on-monitor menu, the safe "remove from library" confirmation and a
lazy preview adapter that uses ``ui/dialogs/preview.py`` when it is available.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core import utils
from core.i18n import tr
from core.logger import get_logger
from core.models import MediaItem
from ui import icons
from ui.components.cards import WallpaperCard
from ui.components.thumbs import ThumbnailWidget
from ui.components.widgets import Badge, EmptyState, h3, text_label
from ui.theme import current_theme

log = get_logger("library-ui")

KIND_LABELS = {"video": "VIDEO", "animation": "ANIMATED", "image": "IMAGE"}


# --------------------------------------------------------------------------- data
def item_kind(item: MediaItem) -> str:
    """Kind of a media row; handles remote rows whose ``format`` is "mp4".

    Mirrors ``MediaItem.kind`` but normalises the format (``"MP4"`` instead of
    ``".mp4"``) and honours ``meta["animated"]`` for static gif/webp pictures.
    """
    from config.constants import ANIMATED_EXTS, VIDEO_EXTS

    fmt = str(item.format or "").strip().lstrip(".").lower()
    if item.file_path:
        ext = os.path.splitext(str(item.file_path))[1].lower()
    else:
        ext = f".{fmt}" if fmt else ""
    animated = item.meta.get("animated") if isinstance(item.meta, dict) else None
    if ext in (".gif", ".webp") and animated is False:
        return "image"
    if ext in ANIMATED_EXTS:
        return "animation"
    if ext in VIDEO_EXTS:
        return "video"
    return "image"


def item_is_local(item: MediaItem) -> bool:
    return bool(item.file_path and os.path.exists(item.file_path))


def media_title(item: MediaItem) -> str:
    return item.title or tr("Untitled")


# -------------------------------------------------------------------------- cards
class LibraryCard(WallpaperCard):
    """WallpaperCard with working favorite button and honest missing-file state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.favorite_button.clicked.connect(self._emit_favorite)
        self.install_button.setToolTip(tr("Choose a monitor to install on"))

    def _emit_favorite(self) -> None:
        if self.item is not None and self.item.id is not None:
            self.favorite_toggled.emit(int(self.item.id))

    def set_item(self, item: MediaItem) -> None:
        super().set_item(item)
        self.setToolTip(media_title(item))
        self.title_label.setToolTip(item.file_path or media_title(item))
        kind = item_kind(item)
        self.kind_badge.setText(tr(KIND_LABELS.get(kind, "FILE")))
        if not item_is_local(item):
            if item.file_path:
                self.kind_badge.setText(tr("MISSING"))
                self.install_button.setEnabled(False)
                self.install_button.setText(tr("Install"))
                self.install_button.setToolTip(tr("The file is missing on disk"))
            else:
                self.install_button.setEnabled(False)
                self.install_button.setText(tr("Not downloaded"))
                self.install_button.setToolTip(tr("Download this wallpaper in Discover first"))
                self.thumb.set_source(item.thumb_path or "", key=f"media:{item.id}")


class FavoriteCard(LibraryCard):
    """Library card for the Favorites collection (may be a remote, not downloaded row)."""

    open_source_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        holder = self.install_button.parentWidget()
        self.source_button = QPushButton(tr("Open source"))
        self.source_button.setObjectName("LinkButton")
        self.source_button.setIcon(icons.icon("external", theme.color("accent"), theme.px(13)))
        self.source_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.source_button.clicked.connect(self._emit_open_source)
        self.source_button.setVisible(False)
        if holder is not None:
            holder.layout().addWidget(self.source_button, 0, Qt.AlignmentFlag.AlignLeft)

    def _emit_open_source(self) -> None:
        if self.item is not None and self.item.id is not None:
            self.open_source_requested.emit(int(self.item.id))

    def set_item(self, item: MediaItem) -> None:
        super().set_item(item)
        self.source_button.setVisible(bool(item.page_url) and not item_is_local(item))

    def _refresh_favorite_icon(self) -> None:
        # Remote favorites can be removed from the collection too; always offer it.
        theme = current_theme()
        favorite = bool(self.item and self.item.is_favorite)
        self.favorite_button.setIcon(icons.icon(
            "star-filled" if favorite else "star",
            theme.color("accent") if favorite else theme.color("text_dim"),
            theme.px(17),
        ))
        self.favorite_button.setToolTip(tr("Remove from favorites" if favorite
                                           else "Add to favorites"))


class CompactCard(QFrame):
    """One-row card used by the compact library view. Mirrors WallpaperCard's signals."""

    install_requested = Signal(int)
    favorite_toggled = Signal(int)
    menu_requested = Signal(int, QPoint)
    clicked = Signal()

    THUMB_W = 132
    THUMB_H = 74

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self.item: MediaItem | None = None
        self.setObjectName("Card")
        self.setMinimumHeight(theme.px(self.THUMB_H + 20))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(theme.px(10), theme.px(10), theme.px(12), theme.px(10))
        layout.setSpacing(theme.px(12))

        self.thumb = ThumbnailWidget(self.THUMB_W, self.THUMB_H, self)
        layout.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignVCenter)

        column = QVBoxLayout()
        column.setSpacing(theme.px(4))
        self.title_label = h3("")
        column.addWidget(self.title_label)
        self.meta_label = text_label("", "CardMeta")
        column.addWidget(self.meta_label)
        badge_row = QHBoxLayout()
        badge_row.setSpacing(theme.px(6))
        self.kind_badge = Badge("", accent=False)
        self.source_badge = Badge("", accent=True)
        badge_row.addWidget(self.kind_badge)
        badge_row.addWidget(self.source_badge)
        badge_row.addStretch(1)
        column.addLayout(badge_row)
        layout.addLayout(column, 1)

        self.favorite_button = QPushButton()
        self.favorite_button.setObjectName("IconButton")
        self.favorite_button.setFixedSize(theme.px(28), theme.px(28))
        self.favorite_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.favorite_button.clicked.connect(self._emit_favorite)
        layout.addWidget(self.favorite_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.install_button = QPushButton(tr("Install"))
        self.install_button.setObjectName("Primary")
        self.install_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_button.setIcon(icons.icon("play", theme.color("accent_text"),
                                               theme.px(14)))
        self.install_button.clicked.connect(self._emit_install)
        layout.addWidget(self.install_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.more_button = QPushButton()
        self.more_button.setObjectName("IconButton")
        self.more_button.setIcon(icons.icon("settings", theme.color("text_dim"), theme.px(16)))
        self.more_button.setFixedSize(theme.px(28), theme.px(28))
        self.more_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more_button.clicked.connect(self._emit_menu_from_button)
        layout.addWidget(self.more_button, 0, Qt.AlignmentFlag.AlignVCenter)

    # ----------------------------------------------------------------- binding
    def set_item(self, item: MediaItem) -> None:
        theme = current_theme()
        self.item = item
        self.title_label.setText(media_title(item))
        self.title_label.setToolTip(item.file_path or media_title(item))
        self.setToolTip(media_title(item))
        self.thumb.set_source(item.file_path or item.thumb_path or "",
                              key=f"media:{item.id}")
        parts = [item.resolution]
        if item.format:
            parts.append(str(item.format).upper())
        if item.duration:
            parts.append(utils.human_duration(item.duration))
        self.meta_label.setText(" · ".join(p for p in parts if p and p != "—"))
        kind = item_kind(item)
        self.kind_badge.setText(tr(KIND_LABELS.get(kind, "FILE")))
        self.source_badge.setText(item.source.upper() if item.source != "local" else tr("LOCAL"))
        if not item_is_local(item):
            self.kind_badge.setText(tr("MISSING") if not item.file_path else tr("REMOTE"))
            self.install_button.setEnabled(False)
            self.install_button.setToolTip(tr("The file is missing on disk"))
        else:
            self.install_button.setEnabled(True)
            self.install_button.setToolTip(tr("Choose a monitor to install on"))
        self._refresh_favorite_icon()

    def _refresh_favorite_icon(self) -> None:
        theme = current_theme()
        favorite = bool(self.item and self.item.is_favorite)
        self.favorite_button.setIcon(icons.icon(
            "star-filled" if favorite else "star",
            theme.color("accent") if favorite else theme.color("text_dim"),
            theme.px(17),
        ))
        self.favorite_button.setToolTip(tr("Remove from favorites" if favorite
                                           else "Add to favorites"))

    # ----------------------------------------------------------------- actions
    def _emit_favorite(self) -> None:
        if self.item is not None and self.item.id is not None:
            self.favorite_toggled.emit(int(self.item.id))

    def _emit_install(self) -> None:
        if self.item is not None and self.item.id is not None:
            self.install_requested.emit(int(self.item.id))

    def _emit_menu_from_button(self) -> None:
        if self.item is not None and self.item.id is not None:
            self.menu_requested.emit(
                int(self.item.id),
                self.more_button.mapToGlobal(QPoint(0, self.more_button.height())),
            )

    # The compact card is a wide row: any left click that is not a button previews.
    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.RightButton:
            if self.item is not None and self.item.id is not None:
                self.menu_requested.emit(int(self.item.id),
                                         event.globalPosition().toPoint())
            return
        child = self.childAt(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and not isinstance(child, QPushButton):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


# --------------------------------------------------------------- install menu
def _monitor_label(monitor) -> str:
    label = tr("{name} ({resolution})", name=monitor.name, resolution=monitor.resolution)
    if monitor.primary:
        label = tr("{name} ({resolution}) · Primary", name=monitor.name,
                   resolution=monitor.resolution)
    return label


def build_install_menu(ctx, media_id: int, parent: QWidget | None = None) -> QMenu:
    """QMenu with "primary monitor", every monitor and "all monitors" choices."""
    theme = current_theme()
    item = ctx.library.get(int(media_id))
    menu = QMenu(parent)
    menu.setToolTipsVisible(True)
    local = bool(item is not None and item_is_local(item))

    primary_action = menu.addAction(
        icons.icon("play", theme.color("accent"), theme.px(16)),
        tr("Install on primary monitor"),
    )
    primary_action.setEnabled(local)
    primary_action.setData(("monitor", None))
    primary = ctx.monitors.primary()
    if primary is not None:
        primary_action.setText(tr("Install on {name}", name=primary.name))

    monitor_menu = menu.addMenu(
        icons.icon("monitors", theme.color("text"), theme.px(16)),
        tr("Install on monitor"),
    )
    monitor_menu.setEnabled(local)
    monitors = ctx.monitors.monitors()
    if not monitors:
        empty = monitor_menu.addAction(tr("No monitors detected"))
        empty.setEnabled(False)
    for monitor in monitors:
        action = monitor_menu.addAction(
            icons.icon("monitors", theme.color("text"), theme.px(16)),
            _monitor_label(monitor),
        )
        action.setData(("monitor", monitor.key))

    all_action = menu.addAction(
        icons.icon("wall", theme.color("text"), theme.px(16)),
        tr("Install on all monitors"),
    )
    all_action.setEnabled(local)
    all_action.setData(("all", None))
    return menu


def show_install_menu(ctx, media_id: int, global_pos: QPoint,
                      parent: QWidget | None = None) -> None:
    """Show the install menu and apply the chosen action."""
    menu = build_install_menu(ctx, media_id, parent)
    chosen = menu.exec(global_pos)
    if chosen is None:
        return
    data = chosen.data()
    if not isinstance(data, tuple) or len(data) != 2:
        return
    mode, monitor_key = data
    if mode == "all":
        ctx.apply_to_all(int(media_id))
    elif mode == "monitor":
        ctx.install_media(int(media_id), monitor_key)


# ------------------------------------------------------------------- preview
def open_media_preview(ctx, item: MediaItem, parent: QWidget | None = None) -> None:
    """Open the preview dialog (lazy import) or fall back to the system player."""
    if not item_is_local(item):
        if item.page_url:
            utils.open_url(item.page_url)
            ctx.notify(tr("Not downloaded — opened the source page"), "warn")
        else:
            ctx.notify(tr("This wallpaper is not downloaded yet"), "warn")
        return
    path = str(item.file_path or "")
    if item_kind(item) == "video":
        try:
            from ui.dialogs.preview import open_preview as _preview  # lazy: optional module
        except Exception:  # noqa: BLE001 - module may not be implemented yet
            _preview = None
        if _preview is not None:
            try:
                _preview(ctx, item, parent=parent)
                return
            except Exception:  # noqa: BLE001 - never crash the gallery on preview
                log.exception("preview dialog failed for %s", path)
    utils.open_in_explorer(path)


# ------------------------------------------------------- remove confirmation
class RemoveMediaDialog(QDialog):
    """Two-step safe removal: record only by default, file deletion is opt-in."""

    def __init__(self, item: MediaItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self.setWindowTitle(tr("Remove from library"))
        self.setModal(True)
        self.setMinimumWidth(theme.px(420))
        self.delete_file = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(theme.px(20), theme.px(18), theme.px(20), theme.px(16))
        layout.setSpacing(theme.px(10))

        title = h3(tr("Remove “{title}” from your library?", title=media_title(item)))
        title.setWordWrap(True)
        layout.addWidget(title)

        note = text_label(tr("The library entry will be removed. The original file stays "
                             "on your disk unless you explicitly ask to delete it."), "Dim")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.path_label = text_label(item.file_path or "", "Caption")
        self.path_label.setWordWrap(True)
        self.path_label.setVisible(bool(item.file_path))
        layout.addWidget(self.path_label)

        self.file_box = QCheckBox(tr("Also delete the file from disk"))
        self.file_box.setVisible(item_is_local(item))
        self.file_box.toggled.connect(self._on_file_toggled)
        layout.addWidget(self.file_box)

        self.warning_label = text_label(
            tr("This permanently deletes the file from your computer."), "Error")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        buttons = QDialogButtonBox()
        self.cancel_button = buttons.addButton(tr("Cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        self.cancel_button.setObjectName("Outline")
        self.remove_button = buttons.addButton(tr("Remove"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.remove_button.setObjectName("Danger")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _on_file_toggled(self, checked: bool) -> None:
        self.warning_label.setVisible(bool(checked) and self.file_box.isVisible())

    def accept(self) -> None:  # noqa: N802 - Qt API
        if self.file_box.isVisible() and self.file_box.isChecked():
            answer = QMessageBox.warning(
                self,
                tr("Delete the file permanently?"),
                tr("The file will be deleted from disk and cannot be restored:\n\n{path}",
                   path=self.path_label.text()),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                # Fall back to the safe action the user already confirmed: record only.
                self.file_box.setChecked(False)
                self.delete_file = False
                super().accept()
                return
        self.delete_file = self.file_box.isVisible() and self.file_box.isChecked()
        super().accept()


def confirm_remove(parent: QWidget, item: MediaItem) -> tuple[bool, bool]:
    """Returns ``(accepted, delete_file)``; delete_file needs the explicit checkbox."""
    dialog = RemoveMediaDialog(item, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return accepted, bool(dialog.delete_file) if accepted else False


# ---------------------------------------------------------------- empty states
class TwoActionEmptyState(EmptyState):
    """EmptyState with an optional secondary (outline) action button."""

    secondary_clicked = Signal()

    def __init__(self, icon_name: str, title: str, subtitle: str = "",
                 action_text: str = "", secondary_text: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(icon_name, title, subtitle, action_text, parent)
        theme = current_theme()
        self.secondary_button = QPushButton(secondary_text)
        self.secondary_button.setObjectName("Outline")
        self.secondary_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.secondary_button.setVisible(bool(secondary_text))
        self.secondary_button.clicked.connect(self.secondary_clicked.emit)
        self.layout().addWidget(self.secondary_button, 0, Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(theme.px(340))
        # Keep the copy readable: a tidy measure instead of a very narrow wrap.
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setMinimumWidth(theme.px(320))
        self.subtitle_label.setMaximumWidth(theme.px(460))
        self.title_label.setMaximumWidth(theme.px(560))

