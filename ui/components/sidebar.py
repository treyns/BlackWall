"""Left navigation sidebar: brand, grouped pages, status and version."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config.constants import APP_VERSION, SIDEBAR_COLLAPSED_WIDTH, SIDEBAR_WIDTH
from core.i18n import tr
from ui import icons
from ui.branding import logo_pixmap
from ui.theme import current_theme

NAV_ITEMS = [
    ("home", "Home", "home"),
    ("discover", "Discover", "discover"),
    ("import", "Import", "link"),
    ("library", "Library", "library"),
    ("favorites", "Favorites", "star"),
    ("monitors", "Monitors", "monitors"),
    ("performance", "Performance", "performance"),
    ("downloads", "Downloads", "downloads"),
]

NAV_GROUPS = [
    ("Overview", ("home", "discover")),
    ("Media", ("import", "library", "favorites")),
    ("System", ("monitors", "performance", "downloads")),
]


class Sidebar(QFrame):
    navigate = Signal(str)
    settings_clicked = Signal()
    collapse_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        theme = current_theme()
        self._collapsed = False
        self._active = "home"
        self._buttons: dict[str, QPushButton] = {}
        self._group_labels: list[QLabel] = []
        self._aurora = bool(getattr(theme, "is_aurora", False))
        self.setFixedWidth(theme.px(SIDEBAR_WIDTH))

        root = QVBoxLayout(self)
        root.setContentsMargins(theme.px(14), theme.px(20), theme.px(14), theme.px(16))
        root.setSpacing(theme.px(6))

        # ------------------------------------------------------------------ brand
        top = QHBoxLayout()
        top.setSpacing(theme.px(10))
        self.logo = QLabel()
        logo_size = theme.px(38 if self._aurora else 34)
        self.logo.setPixmap(logo_pixmap(logo_size, theme.color("accent")))
        self.logo.setFixedSize(logo_size, logo_size)
        self.logo.setScaledContents(True)
        top.addWidget(self.logo)
        brand_box = QVBoxLayout()
        brand_box.setSpacing(theme.px(0))
        self.wordmark = QLabel("BlackWall")
        self.wordmark.setObjectName("BrandName" if self._aurora else "H2")
        brand_box.addWidget(self.wordmark)
        self.brand_subtitle = QLabel(tr("Aurora"))
        self.brand_subtitle.setObjectName("BrandSub")
        self.brand_subtitle.setVisible(self._aurora)
        brand_box.addWidget(self.brand_subtitle)
        top.addLayout(brand_box)
        top.addStretch(1)
        self.collapse_button = QPushButton()
        self.collapse_button.setObjectName("IconButton")
        self.collapse_button.setIcon(icons.icon("chevron-left", theme.color("text_dim"),
                                                theme.px(17)))
        self.collapse_button.setFixedSize(theme.px(28), theme.px(28))
        self.collapse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.collapse_button.setToolTip(tr("Collapse sidebar"))
        self.collapse_button.clicked.connect(self.toggle_collapsed)
        top.addWidget(self.collapse_button)
        root.addLayout(top)
        root.addSpacing(theme.px(18 if self._aurora else 16))

        # ------------------------------------------------------------------- nav
        self._nav_layout = QVBoxLayout()
        self._nav_layout.setSpacing(theme.px(4 if self._aurora else 3))
        if self._aurora:
            for group, keys in NAV_GROUPS:
                group_label = QLabel(tr(group).upper())
                group_label.setObjectName("NavSection")
                self._group_labels.append(group_label)
                self._nav_layout.addWidget(group_label)
                for key in keys:
                    self._add_nav_button(key)
                self._nav_layout.addSpacing(theme.px(7))
        else:
            for key, _label, _icon_name in NAV_ITEMS:
                self._add_nav_button(key)
        root.addLayout(self._nav_layout)
        root.addStretch(1)

        # ---------------------------------------------------------------- bottom
        if self._aurora:
            self.status_card = QFrame()
            self.status_card.setObjectName("SidebarStatus")
            status_box = QVBoxLayout(self.status_card)
            status_box.setContentsMargins(theme.px(12), theme.px(10),
                                          theme.px(12), theme.px(10))
            status_box.setSpacing(theme.px(2))
            status_row = QHBoxLayout()
            status_row.setSpacing(theme.px(8))
            self.status_dot = _StatusDot()
            status_row.addWidget(self.status_dot)
            self.status_label = QLabel(tr("Starting…"))
            self.status_label.setObjectName("StatusText")
            status_row.addWidget(self.status_label, 1)
            status_box.addLayout(status_row)
            self.status_mode = QLabel(tr("Balanced"))
            self.status_mode.setObjectName("StatusMode")
            status_box.addWidget(self.status_mode)
            root.addWidget(self.status_card)
        else:
            status_row = QHBoxLayout()
            status_row.setSpacing(theme.px(8))
            self.status_dot = _StatusDot()
            status_row.addWidget(self.status_dot)
            self.status_label = QLabel(tr("Starting…"))
            self.status_label.setObjectName("Caption")
            status_row.addWidget(self.status_label, 1)
            root.addLayout(status_row)
            self.status_mode = None

        root.addSpacing(theme.px(6))
        self.settings_button = QPushButton(tr("Settings"))
        self.settings_button.setObjectName("SettingsNav" if self._aurora else "NavButton")
        self.settings_button.setIcon(icons.icon("settings", theme.color("text_dim"),
                                               theme.px(19)))
        self.settings_button.setIconSize(QSize(theme.px(19), theme.px(19)))
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.setMinimumHeight(theme.px(42 if self._aurora else 38))
        self.settings_button.clicked.connect(self.settings_clicked.emit)
        root.addWidget(self.settings_button)

        self.version_label = QLabel(f"v{APP_VERSION}")
        self.version_label.setObjectName("Caption")
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(self.version_label)

        self.set_active("home")

    def _add_nav_button(self, key: str) -> None:
        theme = current_theme()
        label = next(item[1] for item in NAV_ITEMS if item[0] == key)
        button = QPushButton(tr(label))
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIconSize(QSize(theme.px(19), theme.px(19)))
        button.setMinimumHeight(theme.px(46 if self._aurora else 40))
        button.clicked.connect(lambda _=False, k=key: self._on_nav(k))
        self._buttons[key] = button
        self._nav_layout.addWidget(button)

    # ------------------------------------------------------------------ public
    def set_active(self, key: str) -> None:
        self._active = key
        theme = current_theme()
        for name, button in self._buttons.items():
            active = name == key
            button.setChecked(active)
            icon_color = theme.color("accent") if active else theme.color("text_dim")
            icon_name = next(item[2] for item in NAV_ITEMS if item[0] == name)
            button.setIcon(icons.icon(icon_name, icon_color, theme.px(19)))
        settings_active = key == "settings"
        self.settings_button.setStyleSheet(
            f"color: {theme.color('accent') if settings_active else theme.color('text_dim')};"
            if settings_active else "")
        self.settings_button.setIcon(icons.icon(
            "settings",
            theme.color("accent") if settings_active else theme.color("text_dim"),
            theme.px(19)))

    def set_status(self, text: str, state: str = "ok") -> None:
        self.status_label.setText(text)
        self.status_dot.set_state(state)

    def set_mode(self, mode_label: str, fps: int | None = None) -> None:
        if self.status_mode is None:
            return
        text = tr(mode_label)
        if fps:
            text = f"{text} · {fps} FPS"
        self.status_mode.setText(text)

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        theme = current_theme()
        self._collapsed = bool(collapsed)
        self.setFixedWidth(theme.px(SIDEBAR_COLLAPSED_WIDTH if collapsed else SIDEBAR_WIDTH))
        self.wordmark.setVisible(not collapsed)
        self.brand_subtitle.setVisible(bool(self._aurora and not collapsed))
        self.version_label.setVisible(not collapsed)
        self.status_label.setVisible(not collapsed)
        if self.status_mode is not None:
            self.status_mode.setVisible(not collapsed)
        if hasattr(self, "status_card"):
            self.status_card.setVisible(not collapsed or self._aurora)
        for label in self._group_labels:
            label.setVisible(not collapsed)
        self.collapse_button.setVisible(not collapsed)
        self.collapse_button.setIcon(icons.icon(
            "chevron-right" if collapsed else "chevron-left", theme.color("text_dim"),
            theme.px(17)))
        for key, button in self._buttons.items():
            label = next(item[1] for item in NAV_ITEMS if item[0] == key)
            button.setText("" if collapsed else tr(label))
            button.setToolTip(tr(label) if collapsed else "")
            button.setMinimumHeight(theme.px(42))
        self.settings_button.setText("" if collapsed else tr("Settings"))
        self.settings_button.setToolTip(tr("Settings") if collapsed else "")
        if collapsed:
            self.collapse_button.show()
            self.collapse_button.setFixedSize(theme.px(24), theme.px(24))
        self.collapse_toggled.emit(self._collapsed)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    # ---------------------------------------------------------------- internal
    def _on_nav(self, key: str) -> None:
        self.set_active(key)
        self.navigate.emit(key)


class _StatusDot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self.setFixedSize(theme.px(8), theme.px(8))
        self._state = "ok"

    def set_state(self, state: str) -> None:
        self._state = state
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        theme = current_theme()
        colors = {
            "ok": theme.color("success"),
            "warn": theme.color("warning"),
            "off": theme.color("text_dim"),
            "error": theme.color("error"),
            "paused": theme.color("accent"),
        }
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors.get(self._state, theme.color("success"))))
        painter.drawEllipse(self.rect())
        painter.end()
