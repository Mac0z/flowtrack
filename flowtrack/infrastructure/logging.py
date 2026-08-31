"""Diagnostic logging configuration."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flowtrack.infrastructure.paths import log_directory

LOG_FILENAME = "flowtrack.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(directory: Path | None = None, *, level: int = logging.INFO) -> Path:
    """Configure the root logger with one rotating UTF-8 file handler."""
    destination = directory or log_directory()
    destination.mkdir(parents=True, exist_ok=True)
    log_path = destination / LOG_FILENAME

    root_logger = logging.getLogger()
    for handler in tuple(root_logger.handlers):
        if getattr(handler, "_flowtrack_handler", False):
            root_logger.removeHandler(handler)
            handler.close()

    handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler._flowtrack_handler = True  # type: ignore[attr-defined]
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
    return log_path

