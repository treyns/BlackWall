"""BlackWall logo: a yellow rounded square with a dark play mark.

Used for the sidebar, the window icon and the system tray.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


def logo_pixmap(size: int = 64, accent: str = "#F2C72E", dark: str = "#101113") -> QPixmap:
    ratio = 2
    pix = QPixmap(size * ratio, size * ratio)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(size * ratio / 64.0, size * ratio / 64.0)

    rect = QRectF(2, 2, 60, 60)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, QColor(accent))
    gradient.setColorAt(1.0, QColor(accent).lighter(112))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(gradient)
    p.drawRoundedRect(rect, 16, 16)

    # dark "screen" plate
    p.setBrush(QColor(dark))
    p.drawRoundedRect(QRectF(13, 16, 38, 26), 7, 7)
    # stand
    p.drawRoundedRect(QRectF(28, 44, 8, 4), 2, 2)
    p.drawRoundedRect(QRectF(22, 48, 20, 3), 1.5, 1.5)

    # play mark
    path = QPainterPath()
    path.moveTo(28.5, 23.0)
    path.lineTo(39.5, 29.0)
    path.lineTo(28.5, 35.0)
    path.closeSubpath()
    p.setBrush(QColor(accent))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPath(path)

    p.end()
    pix.setDevicePixelRatio(ratio)
    return pix


def logo_icon(size: int = 64, accent: str = "#F2C72E") -> QIcon:
    return QIcon(logo_pixmap(size, accent))


def wordmark_pixmap(width: int = 190, accent: str = "#F2C72E") -> QPixmap:
    """'BlackWall' wordmark: bold name with an accent dot."""
    ratio = 2
    height = 30
    pix = QPixmap(width * ratio, height * ratio)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    p.scale(ratio, ratio)
    font = p.font()
    font.setFamily("Segoe UI")
    font.setPixelSize(22)
    font.setWeight(700)
    font.setLetterSpacing(font.SpacingType.AbsoluteSpacing, 0.2)
    p.setFont(font)
    p.setPen(QPen(QColor("#F2F2F2")))
    p.drawText(QRectF(0, 0, width, height), Qt.AlignmentFlag.AlignVCenter, "BlackWall")
    # accent dot after the wordmark
    metrics = p.fontMetrics()
    text_width = metrics.horizontalAdvance("BlackWall")
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(accent))
    p.drawEllipse(QRectF(text_width + 4, height / 2 - 4, 8, 8))
    p.end()
    pix.setDevicePixelRatio(ratio)
    return pix
