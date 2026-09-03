"""Application bootstrap for the FlowTrack desktop shell."""

import logging
import sys
from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QApplication

from flowtrack import __version__
from flowtrack.infrastructure.logging import configure_logging
from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.infrastructure.paths import default_database_path
from flowtrack.infrastructure.dataset import DatasetPaths, resolve_saved_or_legacy_dataset
from flowtrack.infrastructure.lease import HEARTBEAT_INTERVAL_MS
from flowtrack.application.startup import open_dataset
from flowtrack.persistence.database import session_factory
from flowtrack.application.task_execution import TaskExecutionService
from flowtrack.application.task_queries import TaskQueryService
from flowtrack.ui.theme import apply_theme, get_theme
from flowtrack.ui.windows.main_window import MainWindow
from flowtrack.ui.dialogs.startup import choose_data_directory, decide_startup


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
    paths = resolve_saved_or_legacy_dataset(settings, default_database_path())
    if paths is None:
        selected = choose_data_directory()
        if selected is None:
            logger.info("First-run data selection cancelled")
            return 0
        settings.data_directory = selected
        paths = DatasetPaths(selected)
    logger.info("Selected dataset path: %s", paths.root)
    dataset_session = open_dataset(paths, decide_startup)
    if dataset_session is None:
        logger.info("Dataset startup cancelled")
        return 0
    factory = session_factory(dataset_session.engine)
    window = MainWindow(
        settings, TaskExecutionService(factory), TaskQueryService(factory),
        data_directory=paths.root, read_only=dataset_session.read_only,
    )
    heartbeat = QTimer(application)
    heartbeat.setInterval(HEARTBEAT_INTERVAL_MS)
    failures = 0

    def refresh_lease() -> None:
        nonlocal failures
        try:
            if dataset_session.heartbeat():
                failures = 0
            else:
                failures += 1
                logger.warning("Dataset lease heartbeat was not refreshed")
        except OSError:
            failures += 1
            logger.exception("Dataset lease heartbeat failed")
        if failures == 3:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(window, "Data Safety Warning",
                                "FlowTrack cannot refresh the dataset heartbeat. "
                                "Save work and close the application when practical.")

    if not dataset_session.read_only:
        heartbeat.timeout.connect(refresh_lease)
        heartbeat.start()
        logger.info("Dataset heartbeat started")

    def cleanup() -> None:
        heartbeat.stop()
        logger.info("Dataset heartbeat stopped")
        dataset_session.close()

    application.aboutToQuit.connect(cleanup)
    window.show()
    return application.exec()
