"""Application bootstrap for the FlowTrack desktop shell."""

import logging
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QApplication

from flowtrack import __version__
from flowtrack.infrastructure.identity import APPLICATION_NAME, ORGANIZATION_NAME
from flowtrack.infrastructure.logging import configure_logging
from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.infrastructure.performance import PerformanceDiagnostics
from flowtrack.infrastructure.paths import default_database_path
from flowtrack.infrastructure.dataset import DatasetPaths, resolve_saved_or_legacy_dataset
from flowtrack.infrastructure.lease import HEARTBEAT_INTERVAL_MS
from flowtrack.application.startup import StartupSafetyError, open_dataset
from flowtrack.application.data_safety import DataSafetyService
from flowtrack.application.data_location import (
    DataLocationError, DatasetRelocationService, PreparedMove,
)
from flowtrack.infrastructure.backup import BackupManager
from flowtrack.persistence.database import session_factory
from flowtrack.application.task_execution import TaskExecutionService
from flowtrack.application.task_queries import TaskQueryService
from flowtrack.ui.theme import apply_theme, get_theme
from flowtrack.ui.windows.main_window import MainWindow
from flowtrack.ui.dialogs.startup import choose_data_directory, decide_startup, decide_conflicts


def create_application(arguments: Sequence[str] | None = None) -> QApplication:
    """Create and identify the Qt application without starting its event loop."""
    QCoreApplication.setOrganizationName(ORGANIZATION_NAME)
    QCoreApplication.setApplicationName(APPLICATION_NAME)
    QCoreApplication.setApplicationVersion(__version__)
    return QApplication(list(arguments) if arguments is not None else sys.argv)


def run(arguments: Sequence[str] | None = None) -> int:
    """Run FlowTrack with logged, concise GUI handling for fatal startup errors."""
    try:
        return main(arguments)
    except BaseException:
        try:
            configure_logging()
            logging.getLogger(__name__).exception("Fatal error during FlowTrack startup")
            if os.environ.get("FLOWTRACK_PACKAGING_SMOKE_TEST") == "1":
                return 1
            application = QApplication.instance() or create_application(arguments)
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                None,
                "FlowTrack could not start",
                "FlowTrack could not start. Diagnostic details were written to the "
                "FlowTrack log. Your data has not been intentionally changed.",
            )
            application.processEvents()
        except BaseException:
            # At this point even Qt or the writable log destination is unavailable.
            pass
        return 1


def main(arguments: Sequence[str] | None = None) -> int:
    """Configure services, show the application shell, and run Qt."""
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting FlowTrack %s", __version__)
    if os.environ.get("FLOWTRACK_PACKAGING_SMOKE_TEST") == "1":
        from flowtrack.infrastructure.packaging_smoke import run_packaging_smoke
        run_packaging_smoke()
        logger.info("Packaged runtime smoke check passed")
        return 0
    application = create_application(arguments)
    settings = ApplicationSettings()
    performance = PerformanceDiagnostics(lambda: settings.performance_diagnostics_enabled)
    apply_theme(application, get_theme(settings.theme_id))
    smoke_directory: tempfile.TemporaryDirectory[str] | None = None
    if os.environ.get("FLOWTRACK_PACKAGING_GUI_SMOKE_TEST") == "1":
        smoke_directory = tempfile.TemporaryDirectory(prefix="flowtrack-gui-smoke-")
        paths = DatasetPaths(Path(smoke_directory.name))
    else:
        paths = resolve_saved_or_legacy_dataset(settings, default_database_path())
    if paths is None:
        selected = choose_data_directory()
        if selected is None:
            logger.info("First-run data selection cancelled")
            return 0
        settings.data_directory = selected
        paths = DatasetPaths(selected)
    logger.info("Selected dataset path: %s", paths.root)
    try:
        dataset_session = open_dataset(paths, decide_startup, decide_conflicts=decide_conflicts)
    except StartupSafetyError as error:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(
            None, "Data Safety Error",
            f"{error}\n\nOpen the selected data folder outside FlowTrack to preserve it or "
            "recover from a validated backup, then restart FlowTrack."
        )
        return 1
    if dataset_session is None:
        logger.info("Dataset startup cancelled")
        return 0
    factory = session_factory(dataset_session.engine)
    data_safety = DataSafetyService(
        BackupManager(paths), read_only=dataset_session.read_only,
        close_connections=dataset_session.engine.dispose,
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

    relocation = DatasetRelocationService(paths.root, settings, data_safety)

    def commit_data_location(move: PreparedMove | None, existing: Path | None) -> None:
        """Close all ownership state before copying or committing a restart switch."""
        heartbeat.stop()
        dataset_session.close()
        try:
            if move is not None:
                relocation.complete_move(move)
            elif existing is not None:
                relocation.adopt_existing(existing)
        except DataLocationError:
            # The running service graph is deliberately not reopened or hot-swapped.
            # Let Settings present the error, then quit through normal Qt cleanup.
            QTimer.singleShot(0, application.quit)
            raise

    window = MainWindow(
        settings, TaskExecutionService(factory, performance), TaskQueryService(factory),
        data_directory=paths.root, read_only=dataset_session.read_only,
        data_safety=data_safety, commit_data_location=commit_data_location,
        performance=performance,
    )

    def cleanup() -> None:
        heartbeat.stop()
        logger.info("Dataset heartbeat stopped")
        dataset_session.close()

    application.aboutToQuit.connect(cleanup)
    window.show()
    if smoke_directory is not None:
        QTimer.singleShot(1000, application.quit)
    return application.exec()
