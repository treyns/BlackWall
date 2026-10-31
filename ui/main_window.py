"""Main application window: sidebar, page stack, tray and global status."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.constants import (
    APP_TITLE,
    APP_VERSION,
    PERFORMANCE_MODE_ORDER,
    PERFORMANCE_MODES,
    WINDOW_DEFAULT_SIZE,
    WINDOW_MIN_SIZE,
)
from core.i18n import set_language, tr
from core.logger import get_logger
from system import autostart
from system.tray import TrayIcon
from ui.branding import logo_icon
from ui.components.sidebar import Sidebar
from ui.components.widgets import text_label
from ui.pages.base import BasePage
from ui.pages.discover import DiscoverPage
from ui.pages.downloads import DownloadsPage
from ui.pages.favorites import FavoritesPage
from ui.pages.home import HomePage
from ui.pages.import_link import ImportLinkPage
from ui.pages.library import LibraryPage
from ui.pages.monitors import MonitorsPage
from ui.pages.performance import PerformancePage
from ui.pages.settings import SettingsPage
from ui.theme import current_theme, refresh_widgets

log = get_logger("main-window")

PAGE_CLASSES = [
    HomePage,
    DiscoverPage,
    ImportLinkPage,
    LibraryPage,
    FavoritesPage,
    MonitorsPage,
    PerformancePage,
    DownloadsPage,
    SettingsPage,
]


class MainWindow(QMainWindow):
    def __init__(self, ctx, start_minimized: bool = False) -> None:
        super().__init__()
        self.ctx = ctx
        ctx.main_window = self
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(logo_icon(256, current_theme().color("accent")))
        width, height = WINDOW_MIN_SIZE
        self.setMinimumSize(width, height)
        self._pages: dict[str, tuple[BasePage, QScrollArea]] = {}
        self._page_classes = {page_class.PAGE_KEY: page_class for page_class in PAGE_CLASSES}
        self._current = "home"
        self._tray: TrayIcon | None = None
        self._closing = False
        self._rebuild_pending = False
        self._rebuilding = False

        saved_w = int(ctx.settings.get("window.width", WINDOW_DEFAULT_SIZE[0]) or
                      WINDOW_DEFAULT_SIZE[0])
        saved_h = int(ctx.settings.get("window.height", WINDOW_DEFAULT_SIZE[1]) or
                      WINDOW_DEFAULT_SIZE[1])
        self.resize(max(width, saved_w), max(height, saved_h))

        self._build_ui()
        self._build_tray()
        self._connect_signals()
        self._apply_initial_settings()

        if start_minimized or bool(ctx.settings.get("general.start_minimized", False)):
            self.hide()
        else:
            self.show()
        self.show_page("home")
        self._update_controls()

    # ------------------------------------------------------------------- build
    def _build_ui(self) -> None:
        theme = current_theme()
        central = QWidget()
        central.setObjectName("AppRoot")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.set_collapsed(bool(self.ctx.settings.get("window.sidebar_collapsed", False)))
        # The sidebar is recreated on every theme/language rebuild, so its
        # signals must be connected here (once per instance), not only at startup.
        self.sidebar.navigate.connect(self.show_page)
        self.sidebar.settings_clicked.connect(lambda: self.show_page("settings"))
        self.sidebar.collapse_toggled.connect(self._on_sidebar_collapsed)
        root.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("CentralHost")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        top = QWidget()
        top.setObjectName("TopBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(theme.px(28), theme.px(18), theme.px(28), theme.px(8))
        top_layout.setSpacing(theme.px(14))
        titles = QVBoxLayout()
        titles.setSpacing(theme.px(2))
        self.page_title = text_label("", "H1")
        self.page_subtitle = text_label("", "Dim")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        top_layout.addLayout(titles)
        top_layout.addStretch(1)
        self.status_badge = QLabel(tr("No wallpaper"))
        self.status_badge.setObjectName("BadgeDim")
        top_layout.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        self.pause_button = QPushButton(tr("Pause all"))
        self.pause_button.setObjectName("Outline")
        self.pause_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_button.setToolTip(tr("Pause all monitors"))
        self.pause_button.clicked.connect(self._toggle_pause)
        top_layout.addWidget(self.pause_button, 0, Qt.AlignmentFlag.AlignVCenter)
        content_layout.addWidget(top)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        root.addWidget(content, 1)
        self.setCentralWidget(central)
        self._create_page("home")

    def _create_page(self, key: str) -> BasePage | None:
        """Create a page lazily on first visit (keeps application startup fast)."""
        entry = self._pages.get(key)
        if entry is not None:
            return entry[0]
        page_class = self._page_classes.get(key)
        if page_class is None:
            return None
        page = page_class(self.ctx)
        wrapper = QScrollArea()
        wrapper.setWidgetResizable(True)
        wrapper.setFrameShape(QScrollArea.Shape.NoFrame)
        wrapper.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        wrapper.setWidget(page)
        self.stack.addWidget(wrapper)
        self._pages[key] = (page, wrapper)
        return page

    def _build_tray(self) -> None:
        try:
            self._tray = TrayIcon(self)
            self._tray.open_requested.connect(self.show_from_tray)
            self._tray.pause_requested.connect(self.ctx.wallpaper.pause)
            self._tray.resume_requested.connect(self.ctx.wallpaper.resume)
            self._tray.toggle_mode_requested.connect(self._cycle_mode)
            self._tray.settings_requested.connect(lambda: self.show_page("settings"))
            self._tray.exit_requested.connect(self.quit_app)
            if self._tray.icon.isSystemTrayAvailable() if hasattr(
                    self._tray.icon, "isSystemTrayAvailable") else True:
                self._tray.show()
        except Exception:  # noqa: BLE001
            log.exception("system tray is not available")
            self._tray = None

    def _connect_signals(self) -> None:
        # Context-level signals live for the whole window lifetime. Widgets that
        # are recreated during a rebuild connect their own signals in _build_ui().
        self.ctx.status_changed.connect(self._on_status)
        self.ctx.navigate_requested.connect(self._on_navigate_requested)
        self.ctx.assignments_changed.connect(self._update_controls)
        self.ctx.wallpaper.state_changed.connect(self._update_controls)

    def _on_navigate_requested(self, page_key: str) -> None:
        """A page or the tray asked to open a specific page."""
        if not self.isVisible():
            self.show_from_tray()
        self.show_page(page_key)

    def _apply_initial_settings(self) -> None:
        enabled = bool(self.ctx.settings.get("general.run_at_startup", False))
        if enabled != autostart.is_autostart_enabled():
            autostart.set_autostart(enabled)
        self.ctx.wallpaper.set_mode(str(self.ctx.settings.get("performance.mode", "balanced")))

    # -------------------------------------------------------------------- pages
    def show_page(self, key: str) -> None:
        if key not in self._page_classes:
            return
        if self._create_page(key) is None:
            return
        page, wrapper = self._pages[key]
        index = self.stack.indexOf(wrapper)
        if index < 0:
            return
        self.stack.setCurrentIndex(index)
        self._current = key
        page.on_show()
        self.sidebar.set_active(key)
        self.page_title.setText(tr(page.TITLE))
        self.page_subtitle.setText(tr(page.SUBTITLE) if page.SUBTITLE else "")
        self.page_subtitle.setVisible(bool(page.SUBTITLE))

    def current_page(self) -> str:
        return self._current

    def page(self, key: str) -> BasePage | None:
        entry = self._pages.get(key)
        return entry[0] if entry else None

    def refresh_pages(self) -> None:
        for page, _wrapper in list(self._pages.values()):
            if hasattr(page, "refresh"):
                try:
                    page.refresh()
                except Exception:  # noqa: BLE001
                    log.exception("page refresh failed")

    # ------------------------------------------------------------ theme/language
    def _request_rebuild(self) -> None:
        """Coalesce rebuilds and let popups/animations finish first.

        A full widget rebuild inside a QComboBox popup handler is what made the
        application freeze after changing the accent colour, so the actual
        rebuild is delayed and guarded against re-entrancy.
        """
        if self._rebuild_pending:
            return
        self._rebuild_pending = True
        QTimer.singleShot(180, self._rebuild_after_theme_change)

    def _rebuild_after_theme_change(self) -> None:
        self._rebuild_pending = False
        if self._rebuilding:
            return
        popup = QApplication.activePopupWidget()
        if popup is not None:
            try:
                popup.close()
            except Exception:  # noqa: BLE001
                pass
        self.rebuild_ui()

    def rebuild_ui(self) -> None:
        """Rebuild the whole window after a theme or language change."""
        if self._rebuilding:
            return
        self._rebuilding = True
        try:
            current = self._current
            collapsed = self.sidebar.collapsed
            self._pages.clear()
            old = self.centralWidget()
            self._build_ui()
            self.sidebar.set_collapsed(collapsed)
            if old is not None:
                old.hide()
                old.deleteLater()
            self.show_page(current)
            self._update_controls()
            refresh_widgets(self)
        finally:
            self._rebuilding = False

    def apply_language(self, code: str) -> None:
        set_language(code)
        self.ctx.settings.set("general.language", code)
        self._request_rebuild()

    def apply_theme(self) -> None:
        from ui.theme import apply_theme

        apply_theme(QApplication.instance(), self.ctx.settings)
        self._request_rebuild()

    # ------------------------------------------------------------------- status
    def _on_status(self, text: str, state: str) -> None:
        self.status_badge.setText(tr(text))
        self.status_badge.setObjectName("Badge" if state == "ok" else "BadgeDim")
        refresh_widgets(self.status_badge)
        self.sidebar.set_status(tr(text), state)
        self.sidebar.set_mode(
            tr(PERFORMANCE_MODES[self.ctx.wallpaper.mode]["label"]),
            self.ctx.wallpaper.fps_cap,
        )
        if self._tray is not None:
            self._tray.update_state(
                state == "paused",
                tr(PERFORMANCE_MODES[self.ctx.wallpaper.mode]["label"]),
            )

    def _update_controls(self) -> None:
        try:
            paused = self.ctx.wallpaper.paused
            self.pause_button.setText(tr("Resume all") if paused else tr("Pause all"))
            state = "paused" if paused else "ok"
            self._on_status(self.ctx.wallpaper.status_text(), state)
        except Exception:  # noqa: BLE001
            log.exception("could not update header controls")

    def _toggle_pause(self) -> None:
        if self.ctx.wallpaper.paused:
            self.ctx.wallpaper.resume()
        else:
            self.ctx.wallpaper.pause()
        self._update_controls()

    def _cycle_mode(self) -> None:
        current = self.ctx.wallpaper.mode
        try:
            index = PERFORMANCE_MODE_ORDER.index(current)
        except ValueError:
            index = 1
        new_mode = PERFORMANCE_MODE_ORDER[(index + 1) % len(PERFORMANCE_MODE_ORDER)]
        self.ctx.wallpaper.set_mode(new_mode)
        self.ctx.settings.set("performance.mode", new_mode)
        if self._tray is not None:
            self._tray.update_state(self.ctx.wallpaper.paused,
                                    tr(PERFORMANCE_MODES[new_mode]["label"]))

    def _on_sidebar_collapsed(self, collapsed: bool) -> None:
        self.ctx.settings.set("window.sidebar_collapsed", collapsed)

    # ------------------------------------------------------------------- window
    def show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def show_from_tray_if_hidden(self) -> None:
        if not self.isVisible():
            self.showNormal()
        self.raise_()

    def quit_app(self) -> None:
        self._closing = True
        self._save_window_state()
        try:
            self.ctx.shutdown()
        finally:
            if self._tray is not None:
                self._tray.hide()
            QApplication.instance().quit()

    def _save_window_state(self) -> None:
        try:
            self.ctx.settings.set("window.width", self.width())
            self.ctx.settings.set("window.height", self.height())
            self.ctx.settings.set("window.sidebar_collapsed", self.sidebar.collapsed)
        except Exception:  # noqa: BLE001
            pass

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self._closing:
            event.accept()
            return
        if bool(self.ctx.settings.get("general.close_to_tray", True)) and self._tray is not None:
            event.ignore()
            self.hide()
            self._save_window_state()
            self._tray.show_message(
                "BlackWall", tr("BlackWall is still running in the system tray. "
                                "Wallpapers keep playing."))
            return
        event.accept()
        self.quit_app()
