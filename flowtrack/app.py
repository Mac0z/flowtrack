"""Application bootstrap for the FlowTrack desktop shell."""

import logging
import sys
from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from flowtrack import __version__
from flowtrack.infrastructure.logging import configure_logging
from flowtrack.ui.windows.main_window import MainWindow


def create_application(arguments: Sequence[str] | None = None) -> QApplication:
    """Create and identify the Qt application without starting its event loop."""
    QCoreApplication.setOrganizationName("FlowTrack")
    QCoreApplication.setApplicationName("FlowTrack")
    QCoreApplication.setApplicationVersion(__version__)
    return QApplication(list(arguments) if arguments is not None else sys.argv)


def main(arguments: Sequence[str] | None = None) -> int:
    """Configure services, show the application shell, and run Qt."""
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting FlowTrack %s", __version__)
    application = create_application(arguments)
    window = MainWindow()
    window.show()
    return application.exec()

