"""Monitors page: visual layout, per-monitor wallpapers and toggles."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config.constants import FIT_MODE_ORDER, FIT_MODES
from core.i18n import tr
from core.models import Assignment, MonitorInfo
from ui import icons
from ui.components.thumbs import ThumbnailWidget
from ui.components.widgets import (
    Badge,
    Card,
    EmptyState,
    SectionHeader,
    ToggleSwitch,
    dim,
    h3,
    text_label,
)
from ui.pages.base import BasePage
from ui.theme import current_theme


class MonitorDiagram(QWidget):
    monitor_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(230)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._monitors: list[MonitorInfo] = []
        self._selected: str = ""
        self._assignments: dict[str, Assignment] = {}
        self._rects: dict[str, QRectF] = {}
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_monitors(self, monitors: list[MonitorInfo], selected: str,
                     assignments: dict[str, Assignment]) -> None:
        self._monitors = list(monitors)
        self._selected = selected
        self._assignments = assignments
        self.update()

    def _layout_rects(self) -> dict[str, QRectF]:
        theme = current_theme()
        if not self._monitors:
            return {}
        margin = theme.px(18)
        available_w = max(50.0, self.width() - margin * 2)
        available_h = max(50.0, self.height() - margin * 2)
        min_x = min(monitor.x for monitor in self._monitors)
        min_y = min(monitor.y for monitor in self._monitors)
        max_x = max(monitor.x + monitor.width for monitor in self._monitors)
        max_y = max(monitor.y + monitor.height for monitor in self._monitors)
        span_x = max(1, max_x - min_x)
        span_y = max(1, max_y - min_y)
        scale = min(available_w / span_x, available_h / span_y)
        offset_x = margin + (available_w - span_x * scale) / 2
        offset_y = margin + (available_h - span_y * scale) / 2
        rects: dict[str, QRectF] = {}
        for monitor in self._monitors:
            rects[monitor.key] = QRectF(
                offset_x + (monitor.x - min_x) * scale,
                offset_y + (monitor.y - min_y) * scale,
                monitor.width * scale,
                monitor.height * scale,
            )
        return rects

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        theme = current_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(theme.color("card")))
        rects = self._layout_rects()
        self._rects = rects
        if not rects:
            painter.setPen(QPen(QColor(theme.color("text_dim"))))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             tr("No monitors detected"))
            painter.end()
            return
        font = painter.font()
        for monitor in self._monitors:
            rect = rects[monitor.key]
            selected = monitor.key == self._selected
            assignment = self._assignments.get(monitor.key)
            border = theme.color("accent") if selected else theme.color("border")
            fill = QColor(theme.color("selection") if selected else theme.color("surface"))
            painter.setPen(QPen(QColor(border), 2 if selected else 1))
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, theme.px(8), theme.px(8))
            inner = rect.adjusted(4, 4, -4, -theme.px(18))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.color("bg")))
            painter.drawRoundedRect(inner, theme.px(5), theme.px(5))
            stand_w = max(10.0, rect.width() * 0.14)
            painter.setBrush(QColor(theme.color("border")))
            painter.drawRect(QRectF(rect.center().x() - stand_w / 2,
                                    rect.bottom() - theme.px(16), stand_w, theme.px(6)))
            font.setPixelSize(max(9, theme.px(11)))
            painter.setFont(font)
            painter.setPen(QPen(QColor(theme.color("text"))))
            painter.drawText(rect.adjusted(8, 4, -8, -4), Qt.AlignmentFlag.AlignTop
                             | Qt.AlignmentFlag.AlignLeft, monitor.name)
            painter.setPen(QPen(QColor(theme.color("text_dim"))))
            painter.drawText(rect.adjusted(8, 4, -8, -4), Qt.AlignmentFlag.AlignBottom
                             | Qt.AlignmentFlag.AlignLeft,
                             f"{monitor.resolution} · {monitor.refresh:.0f} Hz")
            if assignment and assignment.file_path:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(theme.color("success")))
                painter.drawEllipse(QPointF(rect.right() - theme.px(12),
                                            rect.top() + theme.px(12)),
                                    theme.px(3), theme.px(3))
            if monitor.primary:
                painter.setPen(QPen(QColor(theme.color("accent"))))
                font.setPixelSize(max(9, theme.px(10)))
                painter.setFont(font)
                painter.drawText(rect.adjusted(8, 4, -12, -6), Qt.AlignmentFlag.AlignBottom
                                 | Qt.AlignmentFlag.AlignRight, tr("PRIMARY"))
        painter.end()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        position = event.position()
        for key, rect in self._rects.items():
            if rect.contains(position):
                self.monitor_clicked.emit(key)
                return
        super().mouseReleaseEvent(event)


class MonitorCard(Card):
    def __init__(self, page: "MonitorsPage", monitor: MonitorInfo,
                 assignment: Assignment | None) -> None:
        super().__init__()
        self.page = page
        self.monitor = monitor
        theme = current_theme()
        self.setMinimumWidth(theme.px(330))

        header = QHBoxLayout()
        header.setSpacing(theme.px(8))
        header.addWidget(h3(monitor.name))
        header.addStretch(1)
        if monitor.primary:
            header.addWidget(Badge(tr("Primary")))
        self.body.addLayout(header)

        self.body.addWidget(dim(f"{monitor.resolution} · {monitor.refresh:.0f} Hz"))
        self.wallpaper_line = dim("")
        self.body.addWidget(self.wallpaper_line)

        preview_row = QHBoxLayout()
        preview_row.setSpacing(theme.px(10))
        self.thumb = ThumbnailWidget(140, 79)
        preview_row.addWidget(self.thumb)
        info_box = QVBoxLayout()
        info_box.setSpacing(theme.px(3))
        self.wallpaper_title = text_label(tr("No wallpaper"), "CardTitle")
        info_box.addWidget(self.wallpaper_title)
        self.wallpaper_meta = text_label("", "CardMeta")
        info_box.addWidget(self.wallpaper_meta)
        info_box.addStretch(1)
        preview_row.addLayout(info_box, 1)
        self.body.addLayout(preview_row)

        actions = QHBoxLayout()
        actions.setSpacing(theme.px(6))
        self.choose_button = QPushButton(tr("Choose wallpaper"))
        self.choose_button.setObjectName("Outline")
        self.choose_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.choose_button.clicked.connect(self._choose)
        actions.addWidget(self.choose_button)
        self.remove_button = QPushButton(tr("Remove"))
        self.remove_button.setObjectName("Ghost")
        self.remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_button.clicked.connect(self._remove)
        actions.addWidget(self.remove_button)
        actions.addStretch(1)
        self.body.addLayout(actions)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(theme.px(8))
        toggle_row.addWidget(dim(tr("Enabled on this monitor")))
        toggle_row.addStretch(1)
        self.toggle = ToggleSwitch()
        self.toggle.toggled.connect(self._toggle_enabled)
        toggle_row.addWidget(self.toggle)
        self.body.addLayout(toggle_row)

        paused_row = QHBoxLayout()
        paused_row.setSpacing(theme.px(8))
        paused_row.addWidget(dim(tr("Paused on this monitor")))
        paused_row.addStretch(1)
        self.pause_toggle = ToggleSwitch()
        self.pause_toggle.toggled.connect(self._toggle_paused)
        paused_row.addWidget(self.pause_toggle)
        self.body.addLayout(paused_row)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(theme.px(8))
        mode_row.addWidget(dim(tr("Display mode")))
        mode_row.addStretch(1)
        self.fit_combo = QComboBox()
        for key in FIT_MODE_ORDER:
            self.fit_combo.addItem(tr(FIT_MODES[key]), key)
        self.fit_combo.setMinimumWidth(theme.px(180))
        self.fit_combo.currentIndexChanged.connect(self._change_fit)
        mode_row.addWidget(self.fit_combo)
        self.body.addLayout(mode_row)

        self.apply_all_button = QPushButton(tr("Apply to all monitors"))
        self.apply_all_button.setObjectName("Ghost")
        self.apply_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_all_button.clicked.connect(self._apply_all)
        self.body.addWidget(self.apply_all_button)

        self._update(assignment)

    def _update(self, assignment: Assignment | None) -> None:
        self.assignment = assignment
        if assignment and assignment.file_path:
            item = self.page.ctx.library.get(assignment.media_id) if assignment.media_id else None
            self.thumb.set_source(assignment.file_path,
                                  key=f"assign:{assignment.media_id or assignment.file_path}")
            self.thumb.setVisible(True)
            self.wallpaper_title.setText(item.title if item else assignment.title or tr("Wallpaper"))
            parts = []
            if item is not None:
                parts.append(item.resolution)
                if item.format:
                    parts.append(str(item.format).upper())
            parts.append(tr("Active") if assignment.enabled else tr("Disabled"))
            self.wallpaper_meta.setText(" · ".join(parts))
            self.wallpaper_line.setText(tr("Wallpaper assigned"))
            self.remove_button.setEnabled(True)
            self.apply_all_button.setEnabled(True)
        else:
            self.thumb.setVisible(False)
            self.wallpaper_title.setText(tr("No wallpaper"))
            self.wallpaper_meta.setText(tr("Choose a wallpaper for this display"))
            self.wallpaper_line.setText(tr("Desktop background"))
            self.remove_button.setEnabled(False)
            self.apply_all_button.setEnabled(False)
        self.toggle.blockSignals(True)
        self.toggle.setChecked(bool(assignment and assignment.enabled))
        self.toggle.setEnabled(assignment is not None)
        self.toggle.blockSignals(False)
        self.pause_toggle.blockSignals(True)
        self.pause_toggle.setChecked(
            bool(assignment and self.page.ctx.wallpaper.monitor_paused(self.monitor.key)))
        self.pause_toggle.setEnabled(bool(assignment and assignment.file_path))
        self.pause_toggle.blockSignals(False)
        self.fit_combo.blockSignals(True)
        index = self.fit_combo.findData(assignment.fit if assignment else "cover")
        if index >= 0:
            self.fit_combo.setCurrentIndex(index)
        self.fit_combo.blockSignals(False)
        self.fit_combo.setEnabled(bool(assignment and assignment.file_path))

    def _choose(self) -> None:
        self.page.select_monitor(self.monitor.key)
        self.page.ctx.navigate("library")

    def _remove(self) -> None:
        self.page.ctx.wallpaper.remove(self.monitor.key)
        self.page.refresh()

    def _toggle_enabled(self, checked: bool) -> None:
        self.page.ctx.wallpaper.set_monitor_enabled(self.monitor.key, checked)
        self.page.refresh()

    def _toggle_paused(self, checked: bool) -> None:
        if self.assignment is None:
            return
        if self.page.ctx.wallpaper.monitor_paused(self.monitor.key) == bool(checked):
            return
        self.page.ctx.wallpaper.set_monitor_paused(self.monitor.key, bool(checked))

    def _change_fit(self, _index: int) -> None:
        key = str(self.fit_combo.currentData() or "cover")
        self.page.ctx.set_assignment_fit(self.monitor.key, key)
        # The engine emits state_changed, and MonitorsPage.refresh() rebuilds the
        # cards with the updated mode, so no manual refresh is needed here.

    def _apply_all(self) -> None:
        if not self.assignment or self.assignment.media_id is None:
            return
        self.page.ctx.apply_to_all(self.assignment.media_id)
        self.page.refresh()


class MonitorsPage(BasePage):
    PAGE_KEY = "monitors"
    TITLE = "Monitors"
    SUBTITLE = "Displays and their wallpapers"

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        theme = self.theme
        self._selected = ""
        self._cards: list[MonitorCard] = []

        header_row = QHBoxLayout()
        header_row.addWidget(SectionHeader(tr("Display layout"),
                                           tr("Click a display to select it")), 1)
        self.refresh_button = QPushButton(tr("Refresh"))
        self.refresh_button.setObjectName("Outline")
        self.refresh_button.setIcon(icons.icon("refresh", theme.color("text"), theme.px(16)))
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self._refresh_list)
        header_row.addWidget(self.refresh_button)
        self.root.addLayout(header_row)

        diagram_card = Card()
        self.diagram = MonitorDiagram()
        self.diagram.monitor_clicked.connect(self.select_monitor)
        diagram_card.body.addWidget(self.diagram)
        self.root.addWidget(diagram_card)

        self.root.addWidget(SectionHeader(tr("Displays")))
        self.cards_holder = QWidget()
        self.cards_layout = QHBoxLayout(self.cards_holder)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(theme.px(14))
        self.root.addWidget(self.cards_holder)
        self.empty_state = EmptyState(
            "monitors", tr("No monitors detected"),
            tr("Connect a display and press Refresh."), tr("Refresh"))
        self.empty_state.action_clicked.connect(self._refresh_list)
        self.root.addWidget(self.empty_state)
        self.root.addStretch(1)

        ctx.monitors.changed.connect(self.refresh)
        ctx.assignments_changed.connect(self.refresh)
        ctx.wallpaper.state_changed.connect(self.refresh)
        self.refresh()

    def select_monitor(self, key: str) -> None:
        self._selected = key
        self.diagram.set_monitors(self.ctx.monitors.monitors(), key,
                                  self.ctx.wallpaper.assignments())
        self.diagram.update()

    def _refresh_list(self) -> None:
        self.ctx.monitors.refresh(force=True)
        self.refresh()

    def refresh(self) -> None:
        monitors = self.ctx.monitors.monitors()
        assignments = self.ctx.wallpaper.assignments()
        if not self._selected or not any(m.key == self._selected for m in monitors):
            primary = self.ctx.monitors.primary()
            self._selected = primary.key if primary else (monitors[0].key if monitors else "")

        self.diagram.set_monitors(monitors, self._selected, assignments)

        for card in self._cards:
            self.cards_layout.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        for monitor in monitors:
            card = MonitorCard(self, monitor, assignments.get(monitor.key))
            self.cards_layout.addWidget(card, 1)
            self._cards.append(card)
        self.empty_state.setVisible(not monitors)
        self.cards_holder.setVisible(bool(monitors))

    def on_show(self) -> None:
        self.refresh()
