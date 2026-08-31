import logging
from logging.handlers import RotatingFileHandler

from flowtrack.infrastructure.logging import LOG_FILENAME, configure_logging


def test_configure_logging_creates_rotating_log(tmp_path) -> None:
    log_path = configure_logging(tmp_path)
    logging.getLogger("flowtrack.test").warning("diagnostic message")

    assert log_path == tmp_path / LOG_FILENAME
    assert "diagnostic message" in log_path.read_text(encoding="utf-8")
    assert any(
        isinstance(handler, RotatingFileHandler)
        for handler in logging.getLogger().handlers
    )


def test_configure_logging_is_idempotent(tmp_path) -> None:
    configure_logging(tmp_path)
    configure_logging(tmp_path)
    handlers = [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, "_flowtrack_handler", False)
    ]
    assert len(handlers) == 1

