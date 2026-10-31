"""Logging setup: rotating file log + console, with Qt message forwarding."""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from config import paths

_LOGGER_NAME = "blackwall"
_configured = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    if _configured:
        return logger
    paths.ensure_dirs()
    logger.setLevel(level)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            paths.LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:
        pass

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(fmt)
    console.setLevel(logging.WARNING)
    logger.addHandler(console)
    _configured = True
    logger.info("=== BlackWall logging started ===")
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


_QT_MESSAGE_HOOKS: list = []


def add_qt_message_hook(callback) -> None:
    """Register a callback(message, category) receiving raw Qt messages."""
    _QT_MESSAGE_HOOKS.append(callback)


def install_qt_message_handler() -> None:
    """Route Qt warnings into our log file instead of stderr."""
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except ImportError:
        return

    log = get_logger("qt")
    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handler(mode, context, message):  # noqa: ANN001
        log.log(levels.get(mode, logging.INFO), "%s", message)
        category = getattr(context, "category", "") or ""
        for hook in list(_QT_MESSAGE_HOOKS):
            try:
                hook(message, category)
            except Exception:  # noqa: BLE001 - hooks must never break logging
                pass

    qInstallMessageHandler(handler)


def log_file_path() -> Path:
    return paths.LOG_FILE
