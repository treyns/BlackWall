"""Dialog: merge several videos into one wallpaper, auto or manual cuts."""
from __future__ import annotations

import os
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config import paths
from core import utils
from core.i18n import tr
from core.logger import get_logger
from importers.merge import MergeClip, MergeProject
from importers.processing import aspect_ratio, probe_video
from ui import icons
from ui.components.thumbs import ThumbnailWidget
from ui.components.widgets import Badge, caption, dim, h2, h3, text_label
from ui.dialogs.clip_preview import ClipPreviewDialog
from ui.theme import current_theme

log = get_logger("merge-dialog")


class LibraryClipPicker(QDialog):
    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        theme = current_theme()
        self.setWindowTitle(tr("Add videos from the library"))
        self.setMinimumSize(theme.px(560), theme.px(460))
        root = QVBoxLayout(self)
        root.addWidget(h2(tr("Add videos from the library")))
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        for item in ctx.library.list_items(kind="video"):
            if not item.file_path or not os.path.exists(item.file_path):
                continue
            parts = [item.title or tr("Untitled")]
            if item.duration:
                parts.append(utils.human_duration(item.duration))
            if item.width and item.height:
                parts.append(item.resolution)
            entry = QListWidgetItem(" · ".join(parts))
            entry.setData(Qt.ItemDataRole.UserRole, item.file_path)
            entry.setToolTip(item.file_path)
            self.list.addItem(entry)
        root.addWidget(self.list, 1)
        if self.list.count() == 0:
            root.addWidget(caption(tr("No local videos in the library yet.")))
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        preview = QPushButton(tr("Preview"))
        preview.setObjectName("Ghost")
        preview.clicked.connect(self._preview_selected)
        buttons.addWidget(preview)
        cancel = QPushButton(tr("Cancel"))
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        add = QPushButton(tr("Add selected"))
        add.setObjectName("Primary")
        add.clicked.connect(self.accept)
        buttons.addWidget(add)
        root.addLayout(buttons)

    def _preview_selected(self) -> None:
        selected = self.list.selectedItems()
        if not selected:
            return
        path = selected[0].data(Qt.ItemDataRole.UserRole)
        if path:
            ClipPreviewDialog(path, self).exec()

    def selected_paths(self) -> list[str]:
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.list.selectedItems()]


class MergeVideoDialog(QDialog):
    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.theme = current_theme()
        self.clips: list[dict] = []
        self.rows: list[QWidget] = []
        self.media_id: int | None = None
        self._applied_media_id: int | None = None
        self.setWindowTitle(tr("Merge videos"))
        self.setMinimumSize(self.theme.px(760), self.theme.px(720))
        self._build()
        self._connect()
        self._rebuild_rows()

    # ------------------------------------------------------------------- build
    def _build(self) -> None:
        theme = self.theme
        root = QVBoxLayout(self)
        root.setContentsMargins(theme.px(20), theme.px(18), theme.px(20), theme.px(16))
        root.setSpacing(theme.px(10))
        root.addWidget(h2(tr("Merge videos")))
        root.addWidget(caption(tr(
            "Combine several clips into one wallpaper. Automatic mode plays them "
            "in order; manual mode lets you choose the exact start and end frames.")))

        toolbar = QHBoxLayout()
        toolbar.setSpacing(theme.px(8))
        add_library = QPushButton(tr("Add from library"))
        add_library.setObjectName("Outline")
        add_library.setIcon(icons.icon("library", theme.color("text"), theme.px(15)))
        add_library.clicked.connect(self._add_from_library)
        toolbar.addWidget(add_library)
        add_files = QPushButton(tr("Add files"))
        add_files.setObjectName("Ghost")
        add_files.setIcon(icons.icon("folder", theme.color("text_dim"), theme.px(15)))
        add_files.clicked.connect(self._add_files)
        toolbar.addWidget(add_files)
        toolbar.addStretch(1)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(tr("Automatically"), "auto")
        self.mode_combo.addItem(tr("Manually (frames)"), "manual")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        toolbar.addWidget(dim(tr("Mode")))
        toolbar.addWidget(self.mode_combo)
        root.addLayout(toolbar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        holder = QWidget()
        self.rows_layout = QVBoxLayout(holder)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(theme.px(8))
        self.rows_layout.addStretch(1)
        self.scroll.setWidget(holder)
        self.scroll.setMinimumHeight(theme.px(240))
        root.addWidget(self.scroll, 1)

        settings_card = QFrame()
        settings_card.setObjectName("Card")
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(theme.px(14), theme.px(12),
                                           theme.px(14), theme.px(12))
        settings_layout.setSpacing(theme.px(8))
        settings_layout.addWidget(h3(tr("Output settings")))
        row = QHBoxLayout()
        row.setSpacing(theme.px(8))
        row.addWidget(dim(tr("Display")))
        self.monitor_combo = QComboBox()
        for monitor in self.ctx.monitors.monitors():
            self.monitor_combo.addItem(f"{monitor.name} · {monitor.resolution}", monitor.key)
        primary = self.ctx.monitors.primary()
        if primary is not None:
            index = self.monitor_combo.findData(primary.key)
            if index >= 0:
                self.monitor_combo.setCurrentIndex(index)
        row.addWidget(self.monitor_combo)
        row.addSpacing(theme.px(10))
        row.addWidget(dim(tr("Quality")))
        self.quality_combo = QComboBox()
        self.quality_combo.addItem("1080p", 1920)
        self.quality_combo.addItem("720p", 1280)
        self.quality_combo.addItem("480p", 854)
        self.quality_combo.addItem(tr("Original (monitor)"), 0)
        row.addWidget(self.quality_combo)
        row.addSpacing(theme.px(10))
        row.addWidget(dim(tr("FPS")))
        self.fps_combo = QComboBox()
        self.fps_combo.addItem(tr("Original"), 0)
        for value in (60, 30, 15):
            self.fps_combo.addItem(f"{value} FPS", value)
        self.fps_combo.setCurrentIndex(2)  # 30 FPS default
        row.addWidget(self.fps_combo)
        row.addStretch(1)
        settings_layout.addLayout(row)
        title_row = QHBoxLayout()
        title_row.addWidget(dim(tr("Name")))
        self.title_edit = QLineEdit(tr("Merged video"))
        self.title_edit.setMinimumWidth(theme.px(260))
        title_row.addWidget(self.title_edit, 1)
        settings_layout.addLayout(title_row)
        root.addWidget(settings_card)

        self.status = caption("")
        root.addWidget(self.status)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(theme.px(7))
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton(tr("Cancel"))
        self.cancel_button.setObjectName("Ghost")
        self.cancel_button.clicked.connect(self._on_cancel)
        buttons.addWidget(self.cancel_button)
        self.install_button = QPushButton(tr("Install as wallpaper"))
        self.install_button.setObjectName("Outline")
        self.install_button.setIcon(icons.icon("play", theme.color("text"), theme.px(15)))
        self.install_button.clicked.connect(self._install)
        self.install_button.hide()
        buttons.addWidget(self.install_button)
        self.merge_button = QPushButton(tr("Merge"))
        self.merge_button.setObjectName("Primary")
        self.merge_button.clicked.connect(self._merge)
        buttons.addWidget(self.merge_button)
        root.addLayout(buttons)

    def _connect(self) -> None:
        self.ctx.merge.started.connect(self._on_started)
        self.ctx.merge.phase.connect(self._on_phase)
        self.ctx.merge.progress.connect(self._on_progress)
        self.ctx.merge.finished.connect(self._on_finished)
        self.ctx.merge.failed.connect(self._on_failed)
        self.ctx.merge.cancelled.connect(self._on_cancelled)
        self.ctx.library.changed.connect(self._refresh_monitors)

    def _refresh_monitors(self) -> None:
        # Library updates do not affect the monitor list, but keep the dialog
        # responsive if a new display was attached while it is open.
        current = self.monitor_combo.currentData() if hasattr(self, "monitor_combo") else None
        if current is not None and self.monitor_combo.findData(current) < 0:
            self.monitor_combo.clear()
            for monitor in self.ctx.monitors.monitors():
                self.monitor_combo.addItem(f"{monitor.name} · {monitor.resolution}", monitor.key)

    # -------------------------------------------------------------------- rows
    def _on_mode_changed(self, _index: int) -> None:
        manual = self.mode_combo.currentData() == "manual"
        for row in self.rows:
            for spin in row.findChildren(QSpinBox):
                spin.setVisible(manual)

    def _rebuild_rows(self) -> None:
        while self.rows_layout.count() > 1:
            child = self.rows_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        self.rows = []
        for index, clip in enumerate(self.clips):
            row = self._make_clip_row(index, clip)
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
            self.rows.append(row)
        self._on_mode_changed(0)

    def _make_clip_row(self, index: int, clip: dict) -> QWidget:
        theme = self.theme
        row = QFrame()
        row.setObjectName("Surface")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(theme.px(10), theme.px(8), theme.px(10), theme.px(8))
        layout.setSpacing(theme.px(8))
        order = QLabel(str(index + 1))
        order.setObjectName("Dim")
        layout.addWidget(order)
        thumb = ThumbnailWidget(96, 54)
        thumb.set_source(clip["path"], key=f"merge:{clip['path']}")
        layout.addWidget(thumb)
        info = QVBoxLayout()
        info.setSpacing(theme.px(2))
        title = text_label(os.path.basename(clip["path"]), "CardTitle")
        title.setToolTip(clip["path"])
        info.addWidget(title)
        meta = caption(f"{clip['duration']:.1f}s · {clip['width']}×{clip['height']} · "
                       f"{clip['fps']:.0f} FPS")
        info.addWidget(meta)
        layout.addLayout(info, 1)

        preview = QPushButton()
        preview.setObjectName("IconButton")
        preview.setFixedSize(theme.px(28), theme.px(28))
        preview.setIcon(icons.icon("play", theme.color("text"), theme.px(14)))
        preview.setToolTip(tr("Preview clip"))
        preview.clicked.connect(lambda _=False, i=index: self._preview_clip(i))
        layout.addWidget(preview)

        manual = self.mode_combo.currentData() == "manual"
        start_spin = QSpinBox()
        start_spin.setRange(0, max(0, int(clip["frames"])))
        start_spin.setValue(int(clip.get("start", 0)))
        start_spin.setPrefix(tr("From frame") + " ")
        start_spin.setToolTip(tr("Start frame"))
        start_spin.valueChanged.connect(
            lambda value, i=index: self.clips[i].update(start=int(value)))
        layout.addWidget(start_spin)
        end_spin = QSpinBox()
        end_spin.setRange(1, max(1, int(clip["frames"])))
        end_spin.setValue(int(clip.get("end") or int(clip["frames"])))
        end_spin.setPrefix(tr("To frame") + " ")
        end_spin.setToolTip(tr("End frame"))
        end_spin.valueChanged.connect(
            lambda value, i=index: self.clips[i].update(end=int(value)))
        layout.addWidget(end_spin)
        start_spin.setVisible(manual)
        end_spin.setVisible(manual)

        up = QPushButton("↑")
        up.setObjectName("Ghost")
        up.setFixedWidth(theme.px(30))
        up.clicked.connect(lambda _=False, i=index: self._move(i, -1))
        layout.addWidget(up)
        down = QPushButton("↓")
        down.setObjectName("Ghost")
        down.setFixedWidth(theme.px(30))
        down.clicked.connect(lambda _=False, i=index: self._move(i, 1))
        layout.addWidget(down)
        remove = QPushButton("×")
        remove.setObjectName("Ghost")
        remove.setFixedWidth(theme.px(30))
        remove.clicked.connect(lambda _=False, i=index: self._remove(i))
        layout.addWidget(remove)
        return row

    def _move(self, index: int, delta: int) -> None:
        target = index + delta
        if 0 <= target < len(self.clips):
            self.clips[index], self.clips[target] = self.clips[target], self.clips[index]
            self._rebuild_rows()

    def _preview_clip(self, index: int) -> None:
        if not (0 <= index < len(self.clips)):
            return
        clip = self.clips[index]
        dialog = ClipPreviewDialog(clip["path"], self)
        dialog.exec()

    def _remove(self, index: int) -> None:
        if 0 <= index < len(self.clips):
            self.clips.pop(index)
            self._rebuild_rows()

    # ------------------------------------------------------------------- clips
    def _append_paths(self, paths: list[str]) -> None:
        for path in paths:
            if not path or not os.path.exists(path):
                continue
            if any(os.path.normcase(clip["path"]) == os.path.normcase(path)
                   for clip in self.clips):
                continue
            info = probe_video(path)
            if not info.get("width") or not info.get("height") or not info.get("duration"):
                continue
            fps = float(info.get("fps") or 30.0) or 30.0
            frames = max(1, int(round(float(info["duration"]) * fps)))
            self.clips.append({
                "path": path, "width": int(info["width"]), "height": int(info["height"]),
                "duration": float(info["duration"]), "fps": fps, "frames": frames,
                "start": 0, "end": frames,
            })
        self._rebuild_rows()

    def _add_from_library(self) -> None:
        picker = LibraryClipPicker(self.ctx, self)
        if picker.exec():
            self._append_paths(picker.selected_paths())

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("Add videos"), str(paths.DEFAULT_LIBRARY_DIR),
            tr("Video files (*.mp4 *.webm *.mkv *.mov *.m4v);;All files (*.*)"))
        if paths:
            self._append_paths(paths)

    # ------------------------------------------------------------------ action
    def _merge(self) -> None:
        if len(self.clips) < 2:
            self.status.setText(tr("Add at least two videos"))
            return
        monitor = self.ctx.monitors.get(str(self.monitor_combo.currentData() or ""))
        monitor_width = monitor.width if monitor is not None else 1920
        monitor_height = monitor.height if monitor is not None else 1080
        quality_width = int(self.quality_combo.currentData() or 0)
        width = monitor_width if quality_width <= 0 else min(monitor_width, quality_width)
        width = max(2, width // 2 * 2)
        height = max(2, int(round(width * monitor_height / max(1, monitor_width))) // 2 * 2)
        fps_value = int(self.fps_combo.currentData() or 0)
        if fps_value <= 0:
            max_fps = max((float(clip["fps"]) for clip in self.clips), default=30.0)
            fps_value = max(15, min(60, int(round(max_fps))))
        project = MergeProject(
            clips=[MergeClip(path=clip["path"], start_frame=int(clip["start"]),
                             end_frame=int(clip["end"]), fps=float(clip["fps"]),
                             duration=float(clip["duration"]), width=int(clip["width"]),
                             height=int(clip["height"])) for clip in self.clips],
            title=self.title_edit.text().strip() or tr("Merged video"),
            width=width, height=height, fps=fps_value,
            manual=self.mode_combo.currentData() == "manual",
        )
        self.ctx.merge.merge(project)

    def _on_started(self) -> None:
        self.merge_button.setEnabled(False)
        self.install_button.hide()
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.status.setText(tr("Starting…"))

    def _on_phase(self, phase: str) -> None:
        self.status.setText(tr(phase))

    def _on_progress(self, percent: int, text: str) -> None:
        self.progress_bar.setValue(max(0, min(100, int(percent))))
        if text:
            self.status.setText(tr(text))

    def _on_finished(self, media_id: int) -> None:
        self.media_id = int(media_id)
        self.merge_button.setEnabled(True)
        self.progress_bar.hide()
        self.install_button.show()
        self.status.setText(tr("The merged video was added to the library"))
        self.ctx.notify(tr("Merged video added to the library"), "ok")

    def _on_failed(self, message: str) -> None:
        self.merge_button.setEnabled(True)
        self.progress_bar.hide()
        self.status.setText(tr(message))
        self.ctx.notify(tr(message), "error")

    def _on_cancelled(self) -> None:
        self.merge_button.setEnabled(True)
        self.progress_bar.hide()
        self.status.setText(tr("Merge cancelled"))

    def _on_cancel(self) -> None:
        if self.ctx.merge.busy:
            self.ctx.merge.cancel()
        else:
            self.reject()

    def _install(self) -> None:
        if self.media_id:
            self.ctx.install_media(self.media_id)
            self.accept()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.ctx.merge.busy:
            self.ctx.merge.cancel()
        super().closeEvent(event)
