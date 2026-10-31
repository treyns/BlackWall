"""Import page: paste a TikTok / YouTube / Pinterest link and prepare a live wallpaper."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config.constants import IMPORT_SOURCES
from core import utils
from core.i18n import tr
from core.logger import get_logger
from importers.base import LinkInfo, detect_link
from ui import icons
from ui.components.thumbs import ThumbnailWidget
from ui.components.widgets import (
    Badge,
    Card,
    SectionHeader,
    caption,
    dim,
    h2,
    h3,
    text_label,
)
from ui.pages.base import BasePage
from ui.theme import current_theme

log = get_logger("import-page")


class ImportLinkPage(BasePage):
    PAGE_KEY = "import"
    TITLE = "Import by link"
    SUBTITLE = "TikTok, YouTube and Pinterest videos as live wallpapers"

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self._info: LinkInfo | None = None
        self._media_id: int | None = None
        self._link_timer = QTimer(self)
        self._link_timer.setSingleShot(True)
        self._link_timer.setInterval(550)
        self._link_timer.timeout.connect(self._fetch_current_link)
        self._build()
        self._connect()

    # ------------------------------------------------------------------- build
    def _build(self) -> None:
        theme = self.theme
        self.root.setSpacing(theme.px(14))

        # ------------------------------------------------------------ link input
        link_card = Card()
        row = QHBoxLayout()
        row.setSpacing(theme.px(10))
        self.link_edit = QLineEdit()
        self.link_edit.setPlaceholderText(
            tr("Paste a TikTok, YouTube or Pinterest link, for example https://youtu.be/…"))
        self.link_edit.setClearButtonEnabled(True)
        self.link_edit.setMinimumHeight(theme.px(38))
        row.addWidget(self.link_edit, 1)
        self.import_button = QPushButton(tr("Import"))
        self.import_button.setObjectName("Primary")
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_button.setIcon(icons.icon("downloads", theme.color("accent_text"),
                                              theme.px(16)))
        self.import_button.setEnabled(False)
        row.addWidget(self.import_button)
        link_card.body.addLayout(row)

        self.detected_row = QHBoxLayout()
        self.source_badge = Badge("", accent=True)
        self.source_badge.hide()
        self.detected_label = dim("")
        self.detected_row.addWidget(self.source_badge)
        self.detected_row.addWidget(self.detected_label, 1)
        self.file_button = QPushButton(tr("Import file"))
        self.file_button.setObjectName("Ghost")
        self.file_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.file_button.setIcon(icons.icon("folder", theme.color("text_dim"),
                                            theme.px(15)))
        self.detected_row.addWidget(self.file_button)
        link_card.body.addLayout(self.detected_row)
        link_card.body.addWidget(caption(tr(
            "Only public videos are downloaded. DRM-protected, private and "
            "age-restricted videos are not bypassed. Use content you have the "
            "rights to.")))
        link_card.body.addWidget(caption(tr(
            "Audio is preserved in imported videos; enable it in the wallpaper "
            "settings on the Home page.")))
        self.root.addWidget(link_card)

        # ---------------------------------------------------------------- preview
        self.preview_card = Card()
        preview_row = QHBoxLayout()
        preview_row.setSpacing(theme.px(16))
        self.preview = ThumbnailWidget(380, 214)
        preview_row.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)
        info_col = QVBoxLayout()
        info_col.setSpacing(theme.px(6))
        self.info_title = h3(tr("Video information"))
        self.info_title.setWordWrap(True)
        info_col.addWidget(self.info_title)
        self.info_author = dim("")
        info_col.addWidget(self.info_author)
        self.info_meta = dim("")
        info_col.addWidget(self.info_meta)
        self.info_status = caption("")
        info_col.addWidget(self.info_status)
        info_col.addStretch(1)
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(theme.px(8))
        self.open_source_button = QPushButton(tr("Open source page"))
        self.open_source_button.setObjectName("Ghost")
        self.open_source_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_source_button.setIcon(icons.icon("external", theme.color("text"),
                                                    theme.px(14)))
        buttons_row.addWidget(self.open_source_button)
        buttons_row.addStretch(1)
        info_col.addLayout(buttons_row)
        preview_row.addLayout(info_col, 1)
        self.preview_card.body.addLayout(preview_row)
        self.preview_card.hide()
        self.root.addWidget(self.preview_card)

        # --------------------------------------------------------------- progress
        self.progress_card = Card()
        progress_header = QHBoxLayout()
        self.progress_title = h3(tr("Preparing the video"))
        progress_header.addWidget(self.progress_title, 1)
        self.cancel_button = QPushButton(tr("Cancel"))
        self.cancel_button.setObjectName("Ghost")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        progress_header.addWidget(self.cancel_button)
        self.progress_card.body.addLayout(progress_header)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(theme.px(8))
        self.progress_card.body.addWidget(self.progress_bar)
        self.progress_caption = caption(tr("Starting…"))
        self.progress_card.body.addWidget(self.progress_caption)
        self.progress_card.hide()
        self.root.addWidget(self.progress_card)

        # ------------------------------------------------------------------ error
        self.error_card = Card()
        error_header = QHBoxLayout()
        error_header.addWidget(h3(tr("Could not import this video")), 1)
        self.error_badge = Badge(tr("error"), accent=False)
        error_header.addWidget(self.error_badge)
        self.error_card.body.addLayout(error_header)
        self.error_text = text_label("", "Body")
        self.error_text.setWordWrap(True)
        self.error_card.body.addWidget(self.error_text)
        error_buttons = QHBoxLayout()
        error_buttons.setSpacing(theme.px(8))
        self.manual_button = QPushButton(tr("Import a file instead"))
        self.manual_button.setObjectName("Outline")
        self.manual_button.setCursor(Qt.CursorShape.PointingHandCursor)
        error_buttons.addWidget(self.manual_button)
        self.error_source_button = QPushButton(tr("Open source page"))
        self.error_source_button.setObjectName("Ghost")
        self.error_source_button.setCursor(Qt.CursorShape.PointingHandCursor)
        error_buttons.addWidget(self.error_source_button)
        error_buttons.addStretch(1)
        self.error_card.body.addLayout(error_buttons)
        self.error_card.hide()
        self.root.addWidget(self.error_card)

        # ---------------------------------------------------------------- success
        self.success_card = Card()
        success_header = QHBoxLayout()
        success_header.addWidget(h3(tr("Imported to your library")), 1)
        self.success_badge = Badge(tr("ready"), accent=True)
        success_header.addWidget(self.success_badge)
        self.success_card.body.addLayout(success_header)
        self.success_text = text_label("", "Body")
        self.success_text.setWordWrap(True)
        self.success_card.body.addWidget(self.success_text)
        success_buttons = QHBoxLayout()
        success_buttons.setSpacing(theme.px(8))
        self.install_button = QPushButton(tr("Install as wallpaper"))
        self.install_button.setObjectName("Primary")
        self.install_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_button.setIcon(icons.icon("play", theme.color("accent_text"),
                                               theme.px(15)))
        success_buttons.addWidget(self.install_button)
        self.library_button = QPushButton(tr("Open library"))
        self.library_button.setObjectName("Outline")
        self.library_button.setCursor(Qt.CursorShape.PointingHandCursor)
        success_buttons.addWidget(self.library_button)
        success_buttons.addStretch(1)
        self.success_card.body.addLayout(success_buttons)
        self.success_card.hide()
        self.root.addWidget(self.success_card)

        self.root.addStretch(1)

    # ----------------------------------------------------------------- signals
    def _connect(self) -> None:
        self.link_edit.textChanged.connect(self._on_text_changed)
        self.link_edit.returnPressed.connect(self._start_import)
        self.import_button.clicked.connect(self._start_import)
        self.file_button.clicked.connect(self._pick_files)
        self.manual_button.clicked.connect(self._pick_files)
        self.open_source_button.clicked.connect(self._open_source)
        self.error_source_button.clicked.connect(self._open_source)
        self.cancel_button.clicked.connect(self.ctx.imports.cancel)
        self.install_button.clicked.connect(self._install)
        self.library_button.clicked.connect(lambda: self.ctx.navigate("library"))

        self.ctx.imports.info_ready.connect(self._on_info_ready)
        self.ctx.imports.info_failed.connect(self._on_info_failed)
        self.ctx.imports.started.connect(self._on_started)
        self.ctx.imports.phase.connect(self._on_phase)
        self.ctx.imports.progress.connect(self._on_progress)
        self.ctx.imports.finished.connect(self._on_finished)
        self.ctx.imports.failed.connect(self._on_failed)
        self.ctx.imports.cancelled.connect(self._on_cancelled)

    # ------------------------------------------------------------------ helpers
    def _url(self) -> str:
        return self.link_edit.text().strip()

    def _on_text_changed(self, _text: str) -> None:
        link = detect_link(self._url())
        self._info = None
        self._media_id = None
        self.success_card.hide()
        self.error_card.hide()
        self.progress_card.hide()
        self.import_button.setEnabled(False)
        self.preview_card.hide()
        if link is None:
            self.source_badge.hide()
            self.detected_label.setText(tr("Paste a link to start") if not self._url() else
                                        tr("This link is not supported"))
            return
        self.source_badge.setText(tr(IMPORT_SOURCES.get(link.source, link.source)))
        self.source_badge.show()
        self.source_badge.style().unpolish(self.source_badge)
        self.source_badge.style().polish(self.source_badge)
        self.detected_label.setText(tr("Detected: {source}",
                                       source=IMPORT_SOURCES.get(link.source, link.source)))
        self._link_timer.start()

    def _fetch_current_link(self) -> None:
        url = self._url()
        if detect_link(url) is None:
            return
        self.info_status.setText(tr("Fetching video information…"))
        self._set_busy(False)
        self.ctx.imports.fetch_info(url)

    def _set_busy(self, busy: bool) -> None:
        self.import_button.setEnabled(bool(self._info) and not busy)
        self.import_button.setText(tr("Importing…") if busy else tr("Import"))

    def _on_info_ready(self, info) -> None:
        if not isinstance(info, LinkInfo):
            return
        self._info = info
        self.info_title.setText(info.title or tr("Video"))
        self.info_author.setText(tr("Author: {author}", author=info.author) if info.author
                                 else "")
        parts = []
        if info.width and info.height:
            parts.append(info.resolution)
        if info.duration:
            parts.append(utils.human_duration(info.duration))
        if info.fps:
            parts.append(f"{info.fps:.0f} FPS")
        parts.append(tr(IMPORT_SOURCES.get(info.source, info.source)))
        self.info_meta.setText(" · ".join(part for part in parts if part))
        self.info_status.setText(tr("Ready to import"))
        if info.thumbnail_path and os.path.exists(info.thumbnail_path):
            self.preview.set_source(info.thumbnail_path, key=f"import:{info.source}:"
                                                             f"{info.video_id}")
        self.preview_card.show()
        self.import_button.setEnabled(True)
        self.progress_card.hide()
        self.error_card.hide()

    def _on_info_failed(self, message: str) -> None:
        self._info = None
        self.import_button.setEnabled(False)
        self.preview_card.hide()
        self.info_status.setText("")
        self._show_error(tr(message))

    def _show_error(self, message: str) -> None:
        self.error_text.setText(message)
        self.error_card.show()
        self.progress_card.hide()
        self._set_busy(False)

    def _on_started(self) -> None:
        self._set_busy(True)
        self.error_card.hide()
        self.success_card.hide()
        self.progress_card.show()
        self.progress_bar.setValue(0)
        self.progress_title.setText(tr("Preparing the video"))
        self.progress_caption.setText(tr("Starting…"))

    def _on_phase(self, phase: str) -> None:
        self.progress_caption.setText(tr(phase))

    def _on_progress(self, percent: int, text: str) -> None:
        self.progress_bar.setValue(max(0, min(100, int(percent))))
        if text:
            self.progress_caption.setText(tr(text))

    def _on_finished(self, media_id: int, existing: bool) -> None:
        self._media_id = int(media_id)
        self.progress_card.hide()
        self._set_busy(False)
        self.success_card.show()
        item = self.ctx.library.get(media_id) if media_id else None
        title = item.title if item is not None else tr("the video")
        if existing:
            self.success_text.setText(tr("{title} is already in your library", title=title))
            self.success_badge.setText(tr("already"))
        else:
            self.success_text.setText(tr("{title} was imported and added to the library",
                                         title=title))
            self.success_badge.setText(tr("ready"))
        self.success_badge.style().unpolish(self.success_badge)
        self.success_badge.style().polish(self.success_badge)
        self.ctx.notify(tr("Video imported: {title}", title=title), "ok")

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self._show_error(tr(message))
        self.ctx.notify(tr(message), "error")

    def _on_cancelled(self) -> None:
        self._set_busy(False)
        self.progress_card.hide()
        self.progress_caption.setText(tr("Import cancelled"))
        self.ctx.notify(tr("Import cancelled"), "warn")

    # ------------------------------------------------------------------ actions
    def _start_import(self) -> None:
        url = self._url()
        if detect_link(url) is None:
            self._show_error(tr("Paste a link to a TikTok, YouTube or Pinterest video"))
            return
        if self.ctx.imports.busy:
            self._show_error(tr("Another import is already running"))
            return
        if self._info is None:
            self._fetch_current_link()
            return
        self.ctx.settings.set("import.last_url", url)
        self.ctx.imports.start_import(url, self._info)

    def _pick_files(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Import video files"),
            str(self.ctx.settings.get("storage.library_dir", "")) or os.path.expanduser("~"),
            tr("Video files (*.mp4 *.webm *.mkv *.mov *.m4v);;All files (*.*)"))
        if not path:
            return
        if self.ctx.imports.busy:
            self._show_error(tr("Another import is already running"))
            return
        self.ctx.imports.import_local_file(path)

    def _open_source(self) -> None:
        url = ""
        if self._info is not None:
            url = self._info.webpage_url or self._info.url
        if not url:
            link = detect_link(self._url())
            url = self._url() if link is not None else ""
        if url:
            utils.open_url(url)

    def _install(self) -> None:
        if self._media_id:
            self.ctx.install_media(self._media_id)

    def on_show(self) -> None:
        last = str(self.ctx.settings.get("import.last_url", "") or "")
        if last and not self.link_edit.text():
            self.link_edit.setText(last)

