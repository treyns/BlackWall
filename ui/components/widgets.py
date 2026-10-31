"""Reusable UI building blocks for the Premium Dark interface."""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui import icons
from ui.theme import current_theme


# --------------------------------------------------------------------- labels
def text_label(text: str = "", obj: str = "Body", parent: QWidget | None = None) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName(obj)
    label.setWordWrap(False)
    return label


def h1(text: str, parent: QWidget | None = None) -> QLabel:
    return text_label(text, "H1", parent)


def h2(text: str, parent: QWidget | None = None) -> QLabel:
    return text_label(text, "H2", parent)


def h3(text: str, parent: QWidget | None = None) -> QLabel:
    return text_label(text, "H3", parent)


def dim(text: str, parent: QWidget | None = None) -> QLabel:
    return text_label(text, "Dim", parent)


def caption(text: str, parent: QWidget | None = None) -> QLabel:
    label = text_label(text, "Caption", parent)
    label.setWordWrap(True)
    return label


def icon_label(name: str, color: str = "#F2F2F2", size: int = 20) -> QLabel:
    label = QLabel()
    label.setPixmap(icons.pixmap(name, color, size))
    label.setFixedSize(size, size)
    label.setScaledContents(True)
    return label


def elide(label: QLabel, text: str, width: int | None = None) -> None:
    """Set text and elide it to the label width (safe before layout runs)."""
    metrics = label.fontMetrics()
    available = width if width else max(20, label.width())
    label.setText(metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(20, available)))
    label.setToolTip(text)


# --------------------------------------------------------------------- layout
class Card(QFrame):
    """Rounded dark panel with a vertical body layout."""

    def __init__(self, parent: QWidget | None = None, object_name: str = "Card") -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        theme = current_theme()
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(theme.px(18), theme.px(16), theme.px(18), theme.px(16))
        self.body.setSpacing(theme.px(10))


class Divider(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Divider")
        self.setFixedHeight(1)


class SectionHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", right: QWidget | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.px(12))
        text_box = QVBoxLayout()
        text_box.setSpacing(theme.px(3))
        self.title_label = h2(title)
        text_box.addWidget(self.title_label)
        self.subtitle_label = caption(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))
        text_box.addWidget(self.subtitle_label)
        layout.addLayout(text_box, 1)
        if right is not None:
            layout.addWidget(right)

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))


class StatTile(Card):
    def __init__(self, icon_name: str, title: str, value: str = "—",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self.setMinimumHeight(theme.px(84))
        row = QHBoxLayout()
        row.setSpacing(theme.px(12))
        icon_holder = QFrame()
        icon_holder.setObjectName("Surface")
        icon_holder.setFixedSize(theme.px(40), theme.px(40))
        icon_layout = QHBoxLayout(icon_holder)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label = icon_label(icon_name, theme.color("accent"), theme.px(20))
        icon_layout.addWidget(self.icon_label)
        row.addWidget(icon_holder, 0, Qt.AlignmentFlag.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(theme.px(2))
        self.value_label = text_label(value, "Value")
        self.title_label = text_label(title, "CardMeta")
        column.addWidget(self.value_label)
        column.addWidget(self.title_label)
        row.addLayout(column, 1)
        self.body.addLayout(row)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class Badge(QLabel):
    def __init__(self, text: str = "", accent: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Badge" if accent else "BadgeDim")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class EmptyState(QWidget):
    action_clicked = Signal()

    def __init__(self, icon_name: str, title: str, subtitle: str = "",
                 action_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(theme.px(24), theme.px(36), theme.px(24), theme.px(36))
        layout.setSpacing(theme.px(12))
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        holder = QFrame()
        holder.setObjectName("Surface")
        holder.setFixedSize(theme.px(72), theme.px(72))
        holder_layout = QHBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        holder_layout.addWidget(icon_label(icon_name, theme.color("accent"), theme.px(30)))
        layout.addWidget(holder, 0, Qt.AlignmentFlag.AlignCenter)
        self.title_label = h2(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)
        self.subtitle_label = caption(subtitle)
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setVisible(bool(subtitle))
        layout.addWidget(self.subtitle_label)
        self.action_button = QPushButton(action_text)
        self.action_button.setObjectName("Primary")
        self.action_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_button.setVisible(bool(action_text))
        self.action_button.clicked.connect(self.action_clicked.emit)
        layout.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignCenter)

    def set_texts(self, title: str | None = None, subtitle: str | None = None) -> None:
        if title is not None:
            self.title_label.setText(title)
        if subtitle is not None:
            self.subtitle_label.setText(subtitle)
            self.subtitle_label.setVisible(bool(subtitle))


class ToggleSwitch(QAbstractButton):
    """Animated iOS-style switch used across Settings and Performance pages."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(theme.px(46), theme.px(26))
        self._position = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(150 if theme.animations else 0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._on_animated)
        self.toggled.connect(self._on_toggled)

    def _on_animated(self, value) -> None:
        self._position = float(value)
        self.update()

    def _on_toggled(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt API
        super().setChecked(checked)
        self._position = 1.0 if checked else 0.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        theme = current_theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width, height = self.width(), self.height()
        off_color = QColor(theme.color("surface"))
        on_color = QColor(theme.color("accent"))
        if not self.isEnabled():
            off_color = QColor(theme.color("card"))
            on_color = QColor(theme.color("border"))
        mix = self._position
        track = QColor(
            int(off_color.red() + (on_color.red() - off_color.red()) * mix),
            int(off_color.green() + (on_color.green() - off_color.green()) * mix),
            int(off_color.blue() + (on_color.blue() - off_color.blue()) * mix),
        )
        painter.setPen(QPen(QColor(theme.color("border")) if mix < 0.5 else track, 1))
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0.5, 0.5, width - 1, height - 1), height / 2, height / 2)

        knob_diameter = height - theme.px(6)
        travel = width - knob_diameter - theme.px(6)
        x = theme.px(3) + travel * mix
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.color("accent_text")) if mix > 0.5 else QColor(theme.color("text")))
        painter.drawEllipse(QRectF(x, theme.px(3), knob_diameter, knob_diameter))
        painter.end()


class SegmentedControl(QFrame):
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], current: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Surface")
        theme = current_theme()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(theme.px(3), theme.px(3), theme.px(3), theme.px(3))
        layout.setSpacing(theme.px(2))
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for key, label in options:
            button = QPushButton(label)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self._on_clicked(k))
            self._group.addButton(button)
            self._buttons[key] = button
            layout.addWidget(button)
        self.set_current(current or (options[0][0] if options else ""))

    def _on_clicked(self, key: str) -> None:
        self.changed.emit(key)

    def set_current(self, key: str) -> None:
        button = self._buttons.get(key)
        if button is not None:
            button.setChecked(True)

    def current(self) -> str:
        for key, button in self._buttons.items():
            if button.isChecked():
                return key
        return ""


class ChipBar(QWidget):
    """Horizontal row of category chips."""

    chip_clicked = Signal(str)

    def __init__(self, items: list[tuple[str, str]] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(theme.px(8))
        self._buttons: dict[str, QPushButton] = {}
        if items:
            self.set_items(items)

    def set_items(self, items: list[tuple[str, str]]) -> None:
        for button in self._buttons.values():
            self._layout.removeWidget(button)
            button.deleteLater()
        self._buttons.clear()
        for key, label in items:
            button = QPushButton(label)
            button.setObjectName("Chip")
            button.setCheckable(key != "all")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if key == "all":
                button.setChecked(True)
                self._active = "all"
            button.clicked.connect(lambda _=False, k=key: self._on_click(k))
            self._buttons[key] = button
            self._layout.addWidget(button)
        self._layout.addStretch(1)

    def _on_click(self, key: str) -> None:
        for k, button in self._buttons.items():
            button.setChecked(k == key)
        self._active = key
        self.chip_clicked.emit(key)

    def current(self) -> str:
        return getattr(self, "_active", "all")

    def set_current(self, key: str) -> None:
        for k, button in self._buttons.items():
            button.setChecked(k == key)
        self._active = key


class IconButton(QPushButton):
    def __init__(self, name: str, tooltip: str = "", size: int = 32,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self.setObjectName("IconButton")
        self._name = name
        self._icon_size = theme.px(18)
        self.setIcon(icons.icon(name, theme.color("text_dim"), self._icon_size))
        self.setIconSize(QSize(self._icon_size, self._icon_size))
        self.setFixedSize(theme.px(size), theme.px(size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

    def set_icon(self, name: str) -> None:
        theme = current_theme()
        self._name = name
        self.setIcon(icons.icon(name, theme.color("text_dim"), self._icon_size))


class ProgressRow(QWidget):
    """Small labelled progress used in download rows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        from PySide6.QtWidgets import QProgressBar

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.px(4))
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(theme.px(8))
        layout.addWidget(self.bar)
        self.caption = text_label("", "Caption")
        layout.addWidget(self.caption)

    def set_progress(self, fraction: float, caption: str) -> None:
        self.bar.setValue(int(max(0.0, min(1.0, fraction)) * 1000))
        self.caption.setText(caption)

