"""Circular real-time gauges used by the Aurora performance page."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui.theme import current_theme


class MetricGauge(QWidget):
    """A compact circular gauge with a real value in the centre."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self.title = title
        self._percent = 0.0
        self._text = "—"
        self.setMinimumSize(theme.px(150), theme.px(166))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, percent: float, text: str) -> None:
        self._percent = max(0.0, min(100.0, float(percent)))
        self._text = text
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        theme = current_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        size = min(self.width(), self.height() - theme.px(24))
        side = max(theme.px(80), size - theme.px(12))
        left = (self.width() - side) / 2.0
        top = theme.px(8) + max(0, (self.height() - theme.px(24) - side) / 2.0)
        rect = QRectF(left, top, side, side)
        thick = max(5.0, theme.px(8))
        painter.setPen(QPen(QColor(theme.color("border")), thick,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 225 * 16, -270 * 16)
        accent = QColor(theme.color("accent"))
        painter.setPen(QPen(accent, thick, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 225 * 16, int(-270 * 16 * self._percent / 100.0))

        font = theme.font(21, weight=600)
        painter.setFont(font)
        painter.setPen(QColor(theme.color("text")))
        value_rect = QRectF(rect.left(), rect.top() + side * 0.28,
                            side, side * 0.3)
        painter.drawText(value_rect, Qt.AlignmentFlag.AlignCenter, self._text)

        label_font = QFont(theme.font(11))
        painter.setFont(label_font)
        painter.setPen(QColor(theme.color("text_dim")))
        label_rect = QRectF(0, self.height() - theme.px(22), self.width(),
                            theme.px(18))
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, self.title)
        painter.end()
