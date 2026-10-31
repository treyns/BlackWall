"""Downloads page: real queue with progress, pause/resume/cancel/retry."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.models import DownloadTask
from core.utils import free_space_gb, human_duration, human_eta, human_size, human_speed
from ui import icons
from ui.components.widgets import (
    Badge,
    Card,
    EmptyState,
    SectionHeader,
    caption,
    dim,
    h3,
    text_label,
)
from ui.pages.base import BasePage
from ui.theme import current_theme

STATUS_LABELS = {
    "queued": "Queued",
    "downloading": "Downloading",
    "paused": "Paused",
    "completed": "Completed",
    "error": "Error",
    "cancelled": "Cancelled",
}


class DownloadRow(Card):
    def __init__(self, page: "DownloadsPage", task: DownloadTask) -> None:
        super().__init__()
        self.page = page
        self.task = task
        theme = current_theme()

        header = QHBoxLayout()
        header.setSpacing(theme.px(8))
        title = text_label(task.title or tr("Untitled"), "CardTitle")
        header.addWidget(title, 1)
        self.status_badge = Badge(tr(STATUS_LABELS.get(task.status, task.status)),
                                  accent=task.status in ("downloading", "completed"))
        header.addWidget(self.status_badge)
        self.body.addLayout(header)

        meta_parts = []
        if task.source:
            meta_parts.append(task.source.upper())
        if task.total_bytes:
            meta_parts.append(human_size(task.total_bytes))
        if task.status == "downloading":
            meta_parts.append(human_speed(task.speed))
            if task.eta:
                meta_parts.append(human_eta(task.eta) + " " + tr("left"))
        if task.status == "completed" and task.downloaded_bytes:
            meta_parts.append(human_size(task.downloaded_bytes))
        self.body.addWidget(caption(" · ".join(part for part in meta_parts if part)))

        if task.status in ("downloading", "paused", "queued"):
            self.progress = QProgressBar()
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(task.progress * 1000))
            self.progress.setTextVisible(False)
            self.progress.setFixedHeight(theme.px(8))
            self.body.addWidget(self.progress)

        if task.status == "error" and task.error:
            error_label = caption(tr("Error: {message}", message=task.error[:300]))
            error_label.setObjectName("Error")
            self.body.addWidget(error_label)

        actions = QHBoxLayout()
        actions.setSpacing(theme.px(6))
        actions.addStretch(1)
        if task.status in ("downloading", "queued"):
            pause_button = self._button(tr("Pause"), "pause")
            pause_button.clicked.connect(lambda: page.pause(task.id))
            actions.addWidget(pause_button)
            cancel_button = self._button(tr("Cancel"), "close")
            cancel_button.clicked.connect(lambda: page.cancel(task.id))
            actions.addWidget(cancel_button)
        elif task.status == "paused":
            resume_button = self._button(tr("Resume"), "play", primary=True)
            resume_button.clicked.connect(lambda: page.resume(task.id))
            actions.addWidget(resume_button)
            cancel_button = self._button(tr("Cancel"), "close")
            cancel_button.clicked.connect(lambda: page.cancel(task.id))
            actions.addWidget(cancel_button)
        elif task.status == "error":
            retry_button = self._button(tr("Retry"), "refresh", primary=True)
            retry_button.clicked.connect(lambda: page.retry(task.id))
            actions.addWidget(retry_button)
            remove_button = self._button(tr("Remove"), "trash")
            remove_button.clicked.connect(lambda: page.remove(task.id))
            actions.addWidget(remove_button)
        elif task.status == "completed":
            if task.media_id:
                install_button = self._button(tr("Install"), "play", primary=True)
                install_button.clicked.connect(lambda: page.install(task.id))
                actions.addWidget(install_button)
            folder_button = self._button(tr("Open folder"), "folder")
            folder_button.clicked.connect(lambda: page.open_folder(task.id))
            actions.addWidget(folder_button)
            remove_button = self._button(tr("Remove"), "trash")
            remove_button.clicked.connect(lambda: page.remove(task.id))
            actions.addWidget(remove_button)
        else:  # cancelled
            retry_button = self._button(tr("Retry"), "refresh")
            retry_button.clicked.connect(lambda: page.retry(task.id))
            actions.addWidget(retry_button)
            remove_button = self._button(tr("Remove"), "trash")
            remove_button.clicked.connect(lambda: page.remove(task.id))
            actions.addWidget(remove_button)
        self.body.addLayout(actions)

    def _button(self, text: str, icon_name: str, primary: bool = False) -> QPushButton:
        theme = current_theme()
        button = QPushButton(text)
        button.setObjectName("Primary" if primary else "Outline")
        button.setIcon(icons.icon(icon_name, theme.color("accent_text" if primary else "text"),
                                  theme.px(15)))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button


class DownloadsPage(BasePage):
    PAGE_KEY = "downloads"
    TITLE = "Downloads"
    SUBTITLE = "Download queue and history"

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        theme = self.theme
        self._rows: list[DownloadRow] = []
        self._refresh_pending = False

        header = QHBoxLayout()
        header.addWidget(SectionHeader(tr("Download queue"),
                                       tr("Downloads are saved to the downloads folder")))
        header.addStretch(1)
        self.folder_button = QPushButton(tr("Open downloads folder"))
        self.folder_button.setObjectName("Outline")
        self.folder_button.setIcon(icons.icon("folder", theme.color("text"), theme.px(16)))
        self.folder_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_button.clicked.connect(self._open_download_dir)
        header.addWidget(self.folder_button)
        self.clear_button = QPushButton(tr("Clear finished"))
        self.clear_button.setObjectName("Ghost")
        self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_button.clicked.connect(self._clear_finished)
        header.addWidget(self.clear_button)
        self.root.addLayout(header)

        self.summary = dim("")
        self.root.addWidget(self.summary)

        self.rows_holder = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_holder)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(theme.px(10))
        self.rows_layout.addStretch(1)
        self.root.addWidget(self.rows_holder)

        self.empty_state = EmptyState(
            "downloads", tr("Nothing is downloading"),
            tr("Downloads started from Discover appear here."),
            tr("Find wallpapers"))
        self.empty_state.action_clicked.connect(lambda: self.ctx.navigate("discover"))
        self.root.addWidget(self.empty_state)
        self.footer = caption("")
        self.root.addWidget(self.footer)
        self.root.addStretch(1)

        ctx.downloads.changed.connect(self.schedule_refresh)
        self.refresh()

    # ------------------------------------------------------------------ actions
    def schedule_refresh(self) -> None:
        if self._refresh_pending:
            return
        self._refresh_pending = True
        QTimer.singleShot(250, self._do_refresh)

    def _do_refresh(self) -> None:
        self._refresh_pending = False
        self.refresh()

    def pause(self, download_id: int) -> None:
        self.ctx.downloads.pause(download_id)
        self.refresh()

    def resume(self, download_id: int) -> None:
        self.ctx.downloads.resume(download_id)
        self.refresh()

    def cancel(self, download_id: int) -> None:
        self.ctx.downloads.cancel(download_id)
        self.refresh()

    def retry(self, download_id: int) -> None:
        self.ctx.downloads.retry(download_id)
        self.refresh()

    def remove(self, download_id: int) -> None:
        self.ctx.downloads.remove(download_id)
        self.refresh()

    def install(self, download_id: int) -> None:
        task = self.ctx.downloads.get(download_id)
        if task is not None and task.media_id:
            self.ctx.install_media(task.media_id, None)

    def open_folder(self, download_id: int) -> None:
        task = self.ctx.downloads.get(download_id)
        if task is not None and task.dest_path:
            from core.utils import reveal_in_explorer

            reveal_in_explorer(task.dest_path)

    def _open_download_dir(self) -> None:
        from core.utils import open_in_explorer

        open_in_explorer(str(self.ctx.downloads.download_dir()))

    def _clear_finished(self) -> None:
        for task in self.ctx.downloads.tasks():
            if task.status in ("completed", "cancelled") and task.id is not None:
                self.ctx.downloads.remove(task.id)
        self.refresh()

    # ------------------------------------------------------------------ refresh
    def refresh(self) -> None:
        tasks = self.ctx.downloads.tasks()
        self.summary.setText(tr("{active} active · {done} completed · {failed} failed",
                                active=sum(1 for t in tasks if t.status in
                                           ("queued", "downloading", "paused")),
                                done=sum(1 for t in tasks if t.status == "completed"),
                                failed=sum(1 for t in tasks if t.status == "error")))
        self.empty_state.setVisible(not tasks)
        self.rows_holder.setVisible(bool(tasks))

        for row in self._rows:
            self.rows_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        for task in tasks:
            row = DownloadRow(self, task)
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
            self._rows.append(row)
        free = free_space_gb(str(self.ctx.downloads.download_dir()))
        self.footer.setText(tr("Free disk space in the downloads folder: {space:.1f} GB",
                               space=free))

    def on_show(self) -> None:
        self.refresh()
