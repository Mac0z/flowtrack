"""Safe, restart-based changes to the active FlowTrack dataset."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from alembic.script import ScriptDirectory

from flowtrack.application.data_safety import DataSafetyService
from flowtrack.infrastructure.backup import BackupError, check_integrity
from flowtrack.infrastructure.dataset import DatasetPaths
from flowtrack.persistence.database import migration_config, migration_status

logger = logging.getLogger(__name__)


class DataLocationSettings(Protocol):
    data_directory: Path | None


class DataLocationError(RuntimeError):
    """A safe, user-presentable data-location failure."""


@dataclass(frozen=True)
class PreparedMove:
    source: Path
    destination: Path


class DatasetRelocationService:
    """Validate and adopt datasets without opening a second writable engine.

    A move is prepared while the source is open (including its SQLite-native
    safety backup), then completed only after the application closes the source
    DatasetSession.  Only explicitly durable content is copied.
    """

    _DURABLE_DIRECTORIES = ("backups", "attachments")

    def __init__(self, source: Path, settings: DataLocationSettings,
                 data_safety: DataSafetyService | None) -> None:
        self.source = self.normalise(source)
        self._settings = settings
        self._data_safety = data_safety

    @staticmethod
    def normalise(path: Path) -> Path:
        try:
            return Path(path).expanduser().resolve(strict=False)
        except (OSError, RuntimeError) as error:
            raise DataLocationError("The selected folder path is not valid.") from error

    def is_current(self, path: Path) -> bool:
        return os.path.normcase(str(self.normalise(path))) == os.path.normcase(str(self.source))

    def validate_move_destination(self, destination: Path) -> Path:
        target = self.normalise(destination)
        if self.is_current(target):
            raise DataLocationError("That folder is already the current data location.")
        if target.exists() and not target.is_dir():
            raise DataLocationError("The selected data location is not a folder.")
        if (target / "flowtrack.db").exists():
            raise DataLocationError(
                "The selected folder already contains FlowTrack data. Choose a different "
                "folder, or use Existing FlowTrack Data Folder instead."
            )
        for name in self._DURABLE_DIRECTORIES:
            if (target / name).exists():
                raise DataLocationError(
                    f"The selected folder already contains a {name} item. Choose a different folder."
                )
        try:
            target.mkdir(parents=True, exist_ok=True)
            probe = target / ".flowtrack-write-test"
            with probe.open("xb"):
                pass
            probe.unlink()
        except OSError as error:
            raise DataLocationError("The selected folder cannot be created or written to.") from error
        return target

    def prepare_move(self, destination: Path) -> PreparedMove:
        target = self.validate_move_destination(destination)
        if self._data_safety is None or self._data_safety.read_only:
            raise DataLocationError("Current data cannot be moved while FlowTrack is read-only.")
        try:
            self._data_safety.create_manual_backup()
        except (BackupError, OSError) as error:
            raise DataLocationError(
                "FlowTrack could not create and validate the required safety backup."
            ) from error
        return PreparedMove(self.source, target)

    def complete_move(self, move: PreparedMove) -> None:
        """Copy after source-session closure, validate, then persist adoption."""
        target = self.validate_move_destination(move.destination)
        if self.normalise(move.source) != self.source:
            raise DataLocationError("The relocation source no longer matches the active dataset.")
        try:
            staging = Path(tempfile.mkdtemp(prefix=".flowtrack-relocation-", dir=target))
        except OSError as error:
            raise DataLocationError("FlowTrack could not prepare the destination folder.") from error
        try:
            database = move.source / "flowtrack.db"
            if not database.is_file():
                raise DataLocationError("The current FlowTrack database could not be found.")
            shutil.copy2(database, staging / "flowtrack.db")
            for name in self._DURABLE_DIRECTORIES:
                source_item = move.source / name
                if source_item.is_dir():
                    shutil.copytree(source_item, staging / name, copy_function=shutil.copy2)
            self._validate_database(staging / "flowtrack.db")
            if (staging / ".flowtrack-session.json").exists():
                raise DataLocationError("The prepared dataset unexpectedly contains a session lease.")
            os.replace(staging / "flowtrack.db", target / "flowtrack.db")
            for name in self._DURABLE_DIRECTORIES:
                item = staging / name
                if item.exists():
                    os.replace(item, target / name)
            self._adopt(target)
            logger.info("FlowTrack dataset safely copied and selected for restart: %s", target)
        except DataLocationError:
            logger.exception("Dataset relocation validation failed")
            raise
        except OSError as error:
            logger.exception("Dataset relocation copy failed")
            raise DataLocationError("FlowTrack could not safely copy the data to that folder.") from error
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def validate_existing(self, directory: Path) -> Path:
        target = self.normalise(directory)
        if self.is_current(target):
            raise DataLocationError("That folder is already the current data location.")
        if not target.is_dir() or not (target / "flowtrack.db").is_file():
            raise DataLocationError(
                "The selected folder does not contain an existing FlowTrack database."
            )
        self._validate_database(target / "flowtrack.db")
        return target

    def adopt_existing(self, directory: Path) -> None:
        """Persist an already read-only-validated location; startup owns it later."""
        self._adopt(self.validate_existing(directory))

    def _adopt(self, target: Path) -> None:
        try:
            self._settings.data_directory = target
        except OSError as error:
            raise DataLocationError("FlowTrack could not save the new data location.") from error

    @staticmethod
    def _validate_database(database: Path) -> None:
        if not check_integrity(database, full=True).ok:
            raise DataLocationError("The selected FlowTrack database did not pass integrity validation.")
        try:
            current, _head = migration_status(database)
            if current is None or ScriptDirectory.from_config(
                migration_config()
            ).get_revision(current) is None:
                raise DataLocationError("The selected database is not a recognised FlowTrack dataset.")
        except DataLocationError:
            raise
        except Exception as error:
            raise DataLocationError("The selected database migration state could not be read.") from error
