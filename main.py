"""BlackWall entry point.

Run:  python main.py
      python main.py --minimized   (start in the system tray)
"""
from __future__ import annotations

import os
import sys

# Ask Qt's FFmpeg backend to log its hardware-acceleration decision once; the
# Performance page shows the REAL decoder state based on those messages.
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg.hwaccel.debug=true")

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from config import paths  # noqa: E402
from config.constants import APP_NAME, APP_VERSION  # noqa: E402
from config.settings import Settings  # noqa: E402
from core.context import AppContext  # noqa: E402
from core.database import Database  # noqa: E402
from core.i18n import set_language, tr  # noqa: E402
from core.logger import get_logger, install_qt_message_handler, setup_logging  # noqa: E402
from player import decode_info  # noqa: E402
from system.single_instance import SingleInstance  # noqa: E402
from ui.branding import logo_icon  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.splash import StartupSplash  # noqa: E402
from ui.theme import apply_theme  # noqa: E402


def main() -> int:
    paths.ensure_dirs()
    logger = setup_logging()
    install_qt_message_handler()
    decode_info.install()
    logger.info("BlackWall %s starting", APP_VERSION)

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "BlackWall.Aurora")
        except Exception:  # noqa: BLE001 - cosmetic Windows integration
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    settings = Settings()
    set_language(str(settings.get("general.language", "ru")))
    apply_theme(app, settings)
    app.setWindowIcon(QIcon(logo_icon(256)))

    instance = SingleInstance()
    if not instance.acquire():
        return 0

    start_minimized = "--minimized" in sys.argv or "--tray" in sys.argv
    splash: StartupSplash | None = None
    if not start_minimized:
        try:
            splash = StartupSplash()
            splash.show()
            app.processEvents()
        except Exception:  # noqa: BLE001
            logger.exception("could not show the splash screen")
            splash = None

    def set_status(text: str) -> None:
        if splash is not None:
            try:
                splash.set_status(text)
                app.processEvents()
            except Exception:  # noqa: BLE001
                pass

    set_status(tr("Loading data…"))
    database = Database(paths.DATABASE_FILE)
    set_status(tr("Starting interface…"))
    context = AppContext(settings, database)
    window = MainWindow(context, start_minimized=start_minimized)
    instance.activated.connect(window.show_from_tray)

    context.performance.set_fps_provider(context.wallpaper.measured_fps)
    context.performance.start()
    context.monitors.start_watching()
    context.status_changed.emit(context.wallpaper.status_text(),
                                "ok" if not context.wallpaper.paused else "paused")

    set_status(tr("Restoring wallpapers…"))
    QTimer.singleShot(500, context.wallpaper.refresh)
    if splash is not None:
        QTimer.singleShot(1500, splash.finish)

    def on_about_to_quit() -> None:
        try:
            context.shutdown()
        except Exception:  # noqa: BLE001
            logger.exception("shutdown failed")

    app.aboutToQuit.connect(on_about_to_quit)
    logger.info("BlackWall ready")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
