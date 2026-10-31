"""System tray icon and its context menu."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from config.constants import APP_NAME
from core.i18n import tr
from ui import icons
from ui.branding import logo_icon
from ui.theme import current_theme


class TrayIcon(QObject):
    open_requested = Signal()
    pause_requested = Signal()
    resume_requested = Signal()
    toggle_mode_requested = Signal()
    settings_requested = Signal()
    exit_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        theme = current_theme()
        self.icon = QSystemTrayIcon(logo_icon(64, theme.color("accent")), self)
        self.icon.setToolTip(APP_NAME)
        self._menu = QMenu()
        self._build_menu()
        self.icon.setContextMenu(self._menu)
        self.icon.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        self._menu.clear()
        theme = current_theme()
        open_action = self._menu.addAction(tr("Open BlackWall"))
        open_action.triggered.connect(self.open_requested.emit)
        self._menu.addSeparator()
        self.pause_action = self._menu.addAction(tr("Pause wallpapers"))
        self.pause_action.triggered.connect(self.pause_requested.emit)
        self.resume_action = self._menu.addAction(tr("Resume wallpapers"))
        self.resume_action.triggered.connect(self.resume_requested.emit)
        self.mode_action = self._menu.addAction(tr("Switch performance mode"))
        self.mode_action.triggered.connect(self.toggle_mode_requested.emit)
        self._menu.addSeparator()
        settings_action = self._menu.addAction(tr("Settings"))
        settings_action.triggered.connect(self.settings_requested.emit)
        exit_action = self._menu.addAction(tr("Exit"))
        exit_action.triggered.connect(self.exit_requested.emit)

    def show(self) -> None:
        self.icon.show()

    def hide(self) -> None:
        self.icon.hide()

    def show_message(self, title: str, message: str, msecs: int = 3000) -> None:
        try:
            self.icon.showMessage(title, message, self.icon.icon(), msecs)
        except Exception:  # noqa: BLE001
            pass

    def update_state(self, paused: bool, mode_label: str) -> None:
        self.pause_action.setEnabled(not paused)
        self.resume_action.setEnabled(paused)
        self.mode_action.setText(tr("Performance mode: {mode}", mode=mode_label))
        state = tr("paused") if paused else tr("active")
        self.icon.setToolTip(f"{APP_NAME} — {state}")

    def _on_activated(self, reason) -> None:  # noqa: ANN001
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,
                      QSystemTrayIcon.ActivationReason.Trigger):
            self.open_requested.emit()
