"""Application bootstrap for the FlowTrack desktop shell."""

import logging
import sys
from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from flowtrack import __version__
from flowtrack.infrastructure.logging import configure_logging
from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.infrastructure.paths import default_database_path
from flowtrack.persistence.database import create_database_engine, migrate_database, session_factory
from flowtrack.application.task_execution import TaskExecutionService
from flowtrack.application.task_queries import TaskQueryService
from flowtrack.ui.theme import apply_theme, get_theme
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
    settings = ApplicationSettings()
    apply_theme(application, get_theme(settings.theme_id))
    database_path = default_database_path()
    migrate_database(database_path)
    factory = session_factory(create_database_engine(database_path))
    window = MainWindow(settings, TaskExecutionService(factory), TaskQueryService(factory))
    window.show()
    return application.exec()
