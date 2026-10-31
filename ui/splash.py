"""Startup splash: shown while the heavy part of the application is loading."""
from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from config.constants import APP_NAME, APP_VERSION
from core.i18n import tr
from ui.branding import logo_pixmap
from ui.theme import current_theme


class StartupSplash(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        theme = current_theme()
        self._card = QFrame(self)
        self._card.setObjectName("Card")
        self._card.setStyleSheet(
            f"QFrame#Card {{ background-color: {theme.color('card')};"
            f" border: 1px solid {theme.color('border')};"
            f" border-radius: {theme.px(16)}px; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)

        body = QVBoxLayout(self._card)
        body.setContentsMargins(theme.px(22), theme.px(18), theme.px(22), theme.px(18))
        body.setSpacing(theme.px(10))

        header = QHBoxLayout()
        header.setSpacing(theme.px(12))
        logo = QLabel()
        logo.setPixmap(logo_pixmap(theme.px(40), theme.color("accent")))
        logo.setFixedSize(theme.px(40), theme.px(40))
        logo.setScaledContents(True)
        header.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        name = QLabel(APP_NAME)
        name.setObjectName("H2")
        versions = QLabel(f"v{APP_VERSION}")
        versions.setObjectName("Caption")
        titles.addWidget(name)
        titles.addWidget(versions)
        header.addLayout(titles)
        header.addStretch(1)
        body.addLayout(header)

        self.status_label = QLabel(tr("Starting…"))
        self.status_label.setObjectName("Dim")
        body.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(theme.px(6))
        body.addWidget(self.progress)

        self.setFixedSize(theme.px(380), theme.px(150))
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            rect = screen.availableGeometry()
            self.move(rect.center() - self.rect().center())

        self._animation: QPropertyAnimation | None = None

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def finish(self) -> None:
        try:
            theme = current_theme()
            if theme.animations:
                self._animation = QPropertyAnimation(self, b"windowOpacity", self)
                self._animation.setDuration(180)
                self._animation.setStartValue(1.0)
                self._animation.setEndValue(0.0)
                self._animation.finished.connect(self.close)
                self._animation.start()
                QTimer.singleShot(400, self.close)
            else:
                self.close()
        except Exception:  # noqa: BLE001
            self.close()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 170))
        painter.drawRect(self.rect())
        painter.end()
