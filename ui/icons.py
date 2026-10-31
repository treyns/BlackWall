"""Vector icon set drawn with QPainter (no external assets, any colour/size).

All icons are defined on a 24x24 grid and painted with a 1.7 px stroke so the
whole interface shares one visual language.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_STROKE = 1.7


def _rounded(p: QPainter, x: float, y: float, w: float, h: float, r: float = 2.0) -> None:
    p.drawRoundedRect(QRectF(x, y, w, h), r, r)


def _arc(p: QPainter, rect: QRectF, start: float, span: float) -> None:
    p.drawArc(rect, int(start * 16), int(span * 16))


def _draw(name: str, p: QPainter) -> None:
    if name == "home":
        path = QPainterPath()
        path.moveTo(2.8, 11.2)
        path.lineTo(12, 3.2)
        path.lineTo(21.2, 11.2)
        p.drawPath(path)
        path = QPainterPath()
        path.moveTo(5.2, 9.6)
        path.lineTo(5.2, 20.4)
        path.lineTo(18.8, 20.4)
        path.lineTo(18.8, 9.6)
        p.drawPath(path)
        p.drawLine(QPointF(9.6, 20.4), QPointF(9.6, 14.2))
        p.drawLine(QPointF(9.6, 14.2), QPointF(14.4, 14.2))
        p.drawLine(QPointF(14.4, 14.2), QPointF(14.4, 20.4))

    elif name == "discover":
        p.drawEllipse(QRectF(3.0, 3.0, 18.0, 18.0))
        path = QPainterPath()
        path.moveTo(16.2, 7.8)
        path.lineTo(13.1, 13.1)
        path.lineTo(7.8, 16.2)
        path.lineTo(10.9, 10.9)
        path.closeSubpath()
        p.drawPath(path)

    elif name == "library":
        _rounded(p, 3.0, 3.0, 7.4, 7.4, 1.6)
        _rounded(p, 13.6, 3.0, 7.4, 7.4, 1.6)
        _rounded(p, 3.0, 13.6, 7.4, 7.4, 1.6)
        _rounded(p, 13.6, 13.6, 7.4, 7.4, 1.6)

    elif name in ("star", "star-filled"):
        path = QPainterPath()
        cx, cy, outer, inner = 12.0, 12.4, 9.1, 3.9
        for index in range(10):
            radius = outer if index % 2 == 0 else inner
            angle = -math.pi / 2 + index * math.pi / 5
            point = QPointF(cx + radius * math.cos(angle), cy + radius * math.sin(angle))
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        path.closeSubpath()
        if name == "star-filled":
            p.fillPath(path, p.pen().color())
        p.drawPath(path)

    elif name == "monitors":
        _rounded(p, 2.5, 4.0, 13.0, 9.0, 1.6)
        _rounded(p, 8.5, 11.0, 13.0, 9.0, 1.6)
        p.drawLine(QPointF(9.0, 17.5), QPointF(21.0, 17.5))

    elif name in ("performance", "gauge"):
        _arc(p, QRectF(3.2, 4.6, 17.6, 17.6), 210, -240)
        p.drawLine(QPointF(12.0, 13.2), QPointF(16.6, 8.6))
        p.drawEllipse(QPointF(12.0, 13.2), 1.15, 1.15)
        for angle in (-210, -150, -90, -30, 30):
            rad = math.radians(angle)
            p.drawLine(
                QPointF(12 + 8.8 * math.cos(rad), 13.4 + 8.8 * math.sin(rad)),
                QPointF(12 + 7.4 * math.cos(rad), 13.4 + 7.4 * math.sin(rad)))

    elif name == "downloads":
        p.drawLine(QPointF(12.0, 3.4), QPointF(12.0, 14.6))
        path = QPainterPath()
        path.moveTo(7.6, 10.4)
        path.lineTo(12.0, 14.8)
        path.lineTo(16.4, 10.4)
        p.drawPath(path)
        path = QPainterPath()
        path.moveTo(3.8, 17.2)
        path.lineTo(3.8, 20.4)
        path.lineTo(20.2, 20.4)
        path.lineTo(20.2, 17.2)
        p.drawPath(path)

    elif name == "settings":
        for offset, knob in ((4.4, 8.6), (11.8, 15.4), (19.2, 10.0)):
            p.drawLine(QPointF(3.4, offset), QPointF(20.6, offset))
            p.drawEllipse(QPointF(knob, offset), 2.0, 2.0)

    elif name == "plus":
        p.drawLine(QPointF(12.0, 5.0), QPointF(12.0, 19.0))
        p.drawLine(QPointF(5.0, 12.0), QPointF(19.0, 12.0))

    elif name == "minus":
        p.drawLine(QPointF(5.0, 12.0), QPointF(19.0, 12.0))

    elif name == "play":
        path = QPainterPath()
        path.moveTo(8.0, 5.2)
        path.lineTo(19.2, 12.0)
        path.lineTo(8.0, 18.8)
        path.closeSubpath()
        p.fillPath(path, p.pen().color())
        p.drawPath(path)

    elif name == "pause":
        p.drawLine(QPointF(8.6, 5.0), QPointF(8.6, 19.0))
        p.drawLine(QPointF(15.4, 5.0), QPointF(15.4, 19.0))

    elif name == "search":
        p.drawEllipse(QRectF(3.6, 3.6, 12.0, 12.0))
        p.drawLine(QPointF(14.4, 14.4), QPointF(20.4, 20.4))

    elif name == "trash":
        p.drawLine(QPointF(3.6, 6.4), QPointF(20.4, 6.4))
        p.drawLine(QPointF(9.0, 6.4), QPointF(9.0, 3.6))
        p.drawLine(QPointF(9.0, 3.6), QPointF(15.0, 3.6))
        p.drawLine(QPointF(15.0, 3.6), QPointF(15.0, 6.4))
        path = QPainterPath()
        path.moveTo(5.6, 6.4)
        path.lineTo(6.8, 20.4)
        path.lineTo(17.2, 20.4)
        path.lineTo(18.4, 6.4)
        p.drawPath(path)
        p.drawLine(QPointF(10.2, 10.0), QPointF(10.6, 17.0))
        p.drawLine(QPointF(13.8, 10.0), QPointF(13.4, 17.0))

    elif name == "folder":
        path = QPainterPath()
        path.moveTo(3.0, 6.4)
        path.lineTo(9.4, 6.4)
        path.lineTo(11.2, 8.6)
        path.lineTo(21.0, 8.6)
        path.lineTo(21.0, 19.0)
        path.lineTo(3.0, 19.0)
        path.closeSubpath()
        p.drawPath(path)

    elif name == "refresh":
        _arc(p, QRectF(4.2, 4.2, 15.6, 15.6), 40, 280)
        path = QPainterPath()
        path.moveTo(16.4, 2.4)
        path.lineTo(19.6, 5.8)
        path.lineTo(15.0, 6.4)
        p.drawPath(path)

    elif name in ("chevron-left", "chevron-right", "chevron-down", "chevron-up"):
        mapping = {
            "chevron-left": [(15.2, 4.8), (8.4, 12.0), (15.2, 19.2)],
            "chevron-right": [(8.8, 4.8), (15.6, 12.0), (8.8, 19.2)],
            "chevron-down": [(4.8, 9.2), (12.0, 16.0), (19.2, 9.2)],
            "chevron-up": [(4.8, 14.8), (12.0, 8.0), (19.2, 14.8)],
        }
        path = QPainterPath()
        points = mapping[name]
        path.moveTo(*points[0])
        path.lineTo(*points[1])
        path.lineTo(*points[2])
        p.drawPath(path)

    elif name == "link":
        p.save()
        p.translate(12.0, 12.0)
        p.rotate(-45.0)
        p.drawRoundedRect(QRectF(-7.2, -3.0, 7.2, 6.0), 2.6, 2.6)
        p.drawRoundedRect(QRectF(0.0, -3.0, 7.2, 6.0), 2.6, 2.6)
        p.restore()

    elif name == "external":
        p.drawLine(QPointF(4.0, 8.4), QPointF(4.0, 20.0))
        p.drawLine(QPointF(4.0, 20.0), QPointF(15.6, 20.0))
        p.drawLine(QPointF(15.6, 20.0), QPointF(15.6, 12.4))
        p.drawLine(QPointF(10.4, 13.6), QPointF(20.4, 3.6))
        path = QPainterPath()
        path.moveTo(14.0, 3.6)
        path.lineTo(20.4, 3.6)
        path.lineTo(20.4, 10.0)
        p.drawPath(path)

    elif name == "check":
        path = QPainterPath()
        path.moveTo(4.6, 12.4)
        path.lineTo(9.8, 17.6)
        path.lineTo(19.4, 6.6)
        p.drawPath(path)

    elif name in ("close", "x"):
        p.drawLine(QPointF(5.4, 5.4), QPointF(18.6, 18.6))
        p.drawLine(QPointF(18.6, 5.4), QPointF(5.4, 18.6))

    elif name == "image":
        _rounded(p, 3.0, 4.4, 18.0, 15.2, 2.0)
        p.drawEllipse(QPointF(9.0, 9.8), 1.6, 1.6)
        path = QPainterPath()
        path.moveTo(5.4, 17.6)
        path.lineTo(10.2, 12.4)
        path.lineTo(13.2, 15.4)
        path.lineTo(16.2, 12.6)
        path.lineTo(18.8, 16.2)
        p.drawPath(path)

    elif name == "video":
        _rounded(p, 2.6, 5.0, 18.8, 14.0, 2.4)
        path = QPainterPath()
        path.moveTo(10.2, 9.0)
        path.lineTo(15.6, 12.0)
        path.lineTo(10.2, 15.0)
        path.closeSubpath()
        p.drawPath(path)

    elif name in ("volume", "mute"):
        path = QPainterPath()
        path.moveTo(4.0, 9.2)
        path.lineTo(7.4, 9.2)
        path.lineTo(11.6, 5.4)
        path.lineTo(11.6, 18.6)
        path.lineTo(7.4, 14.8)
        path.lineTo(4.0, 14.8)
        path.closeSubpath()
        p.drawPath(path)
        if name == "volume":
            _arc(p, QRectF(11.0, 8.0, 8.4, 8.4), -60, 120)
            _arc(p, QRectF(12.6, 5.4, 12.0, 13.2), -55, 110)
        else:
            p.drawLine(QPointF(15.2, 9.6), QPointF(19.6, 14.4))
            p.drawLine(QPointF(19.6, 9.6), QPointF(15.2, 14.4))

    elif name == "power":
        _arc(p, QRectF(4.4, 4.4, 15.2, 15.2), 40, 280)
        p.drawLine(QPointF(12.0, 2.8), QPointF(12.0, 11.2))

    elif name == "grid":
        for x, y in ((4.0, 4.0), (13.0, 4.0), (4.0, 13.0), (13.0, 13.0)):
            _rounded(p, x, y, 7.0, 7.0, 1.4)

    elif name == "list":
        for index, y in enumerate((6.2, 12.0, 17.8)):
            p.drawEllipse(QPointF(4.6, y), 1.1, 1.1)
            p.drawLine(QPointF(8.4, y), QPointF(20.0, y))

    elif name == "arrow-left":
        p.drawLine(QPointF(20.0, 12.0), QPointF(4.4, 12.0))
        path = QPainterPath()
        path.moveTo(10.6, 5.4)
        path.lineTo(4.0, 12.0)
        path.lineTo(10.6, 18.6)
        p.drawPath(path)

    elif name == "dot":
        color = p.pen().color()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(QPointF(12.0, 12.0), 4.2, 4.2)
        p.setBrush(Qt.BrushStyle.NoBrush)

    elif name == "key":
        p.drawEllipse(QPointF(8.0, 12.0), 3.6, 3.6)
        p.drawLine(QPointF(11.6, 12.0), QPointF(20.4, 12.0))
        p.drawLine(QPointF(17.0, 12.0), QPointF(17.0, 15.4))
        p.drawLine(QPointF(20.4, 12.0), QPointF(20.4, 15.0))

    elif name == "wall":
        _rounded(p, 3.0, 4.0, 18.0, 16.0, 2.2)
        p.drawLine(QPointF(3.0, 9.0), QPointF(21.0, 9.0))
        p.drawLine(QPointF(9.0, 9.0), QPointF(9.0, 20.0))
        p.drawLine(QPointF(15.0, 9.0), QPointF(15.0, 20.0))

    else:  # fallback: a neutral dot
        p.drawEllipse(QPointF(12.0, 12.0), 4.2, 4.2)


def pixmap(name: str, color: str = "#F2F2F2", size: int = 20,
           stroke: float = _STROKE) -> QPixmap:
    ratio = 2  # render at 2x for crisp HiDPI rendering
    pix = QPixmap(size * ratio, size * ratio)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.scale(size * ratio / 24.0, size * ratio / 24.0)
    pen = QPen(QColor(color))
    pen.setWidthF(stroke)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _draw(name, painter)
    painter.end()
    pix.setDevicePixelRatio(ratio)
    return pix


def icon(name: str, color: str = "#F2F2F2", size: int = 20,
         stroke: float = _STROKE) -> QIcon:
    return QIcon(pixmap(name, color, size, stroke))
