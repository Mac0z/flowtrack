"""Testable startup ownership decisions and lifecycle."""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

from sqlalchemy import Engine

from flowtrack.infrastructure.dataset import DatasetPaths
from flowtrack.infrastructure.lease import LeaseState, LeaseStore
from flowtrack.infrastructure.locking import DatasetLock
from flowtrack.infrastructure.backup import (
    BackupError, BackupManager, BackupReason, check_integrity,
)
from flowtrack.persistence.database import (
    create_database_engine, migrate_database, migration_required,
)

logger = logging.getLogger(__name__)


class StartupChoice(Enum):
    WRITE = "write"
    READ_ONLY = "read_only"
    CANCEL = "cancel"


class StartupSafetyError(RuntimeError):
    """Writable startup stopped without changing an unsafe database."""


@dataclass
class DatasetSession:
    paths: DatasetPaths
    instance_id: str
    read_only: bool
    engine: Engine
    lease: LeaseStore
    lock: DatasetLock | None = None
    _closed: bool = False

    def heartbeat(self) -> bool:
        return False if self.read_only else self.lease.heartbeat(self.instance_id)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.engine.dispose()
        if not self.read_only:
            self.lease.release(self.instance_id)
        if self.lock is not None:
            self.lock.release()
        logger.info("Dataset session cleanup complete")


Decision = Callable[[LeaseState], StartupChoice]


def open_dataset(
    paths: DatasetPaths,
    decide: Decision,
    *,
    instance_id: str | None = None,
    migrate: Callable[[Path], None] = migrate_database,
    lock_factory: Callable[[Path], DatasetLock] = DatasetLock,
    now: datetime | None = None,
    backup_manager_factory: Callable[[DatasetPaths], BackupManager] = BackupManager,
    needs_migration: Callable[[Path], bool] = migration_required,
) -> DatasetSession | None:
    """Open a dataset only after the caller explicitly resolves safety states."""
    paths.initialise()
    identity = instance_id or str(uuid.uuid4())
    lease = LeaseStore(paths.session_lease)
    evaluation = lease.evaluate(identity, now=now)
    logger.info("Dataset %s lease state: %s", paths.root, evaluation.state.value)

    choice = StartupChoice.WRITE if evaluation.state in {
        LeaseState.ABSENT, LeaseState.OWNED_BY_THIS_INSTANCE
    } else decide(evaluation.state)
    if choice is StartupChoice.CANCEL:
        return None
    if choice is StartupChoice.READ_ONLY:
        engine = create_database_engine(paths.database, read_only=True)
        logger.info("Opening dataset %s read-only", paths.root)
        return DatasetSession(paths, identity, True, engine, lease)

    # Active foreign leases can never be overridden, even by a faulty UI callback.
    if evaluation.state is LeaseState.ACTIVE_OTHER_INSTANCE:
        return None
    if evaluation.state in {LeaseState.STALE_OTHER_INSTANCE, LeaseState.MALFORMED}:
        logger.warning("User explicitly selected lease recovery (%s)", evaluation.state.value)
    lock = lock_factory(paths.root)
    if not lock.acquire():
        logger.warning("Local dataset lock rejected for %s", paths.root)
        choice = decide(LeaseState.ACTIVE_OTHER_INSTANCE)
        if choice is not StartupChoice.READ_ONLY:
            return None
        return DatasetSession(paths, identity, True,
                              create_database_engine(paths.database, read_only=True), lease)
    logger.info("Local dataset lock acquired for %s", paths.root)
    try:
        lease.claim(identity)
        manager = backup_manager_factory(paths)
        existing = paths.database.is_file() and paths.database.stat().st_size > 0
        if existing and not check_integrity(paths.database).ok:
            raise StartupSafetyError(
                "FlowTrack found a problem with the selected database and has not opened it "
                "for writing. Your original data has not been replaced."
            )
        if existing and needs_migration(paths.database):
            logger.info("Creating required pre-migration backup")
            try:
                manager.create(BackupReason.MIGRATION, now=now)
            except BackupError as error:
                raise StartupSafetyError(
                    "FlowTrack could not create the required migration backup. The database "
                    "was not migrated."
                ) from error
        migrate(paths.database)
        database_ready = paths.database.is_file() and paths.database.stat().st_size > 0
        if database_ready and not check_integrity(paths.database).ok:
            raise StartupSafetyError(
                "FlowTrack could not validate the database after migration and has not opened it."
            )
        engine = create_database_engine(paths.database)
        if database_ready:
            try:
                manager.create_daily_if_needed(now=now)
            except BackupError as error:
                engine.dispose()
                raise StartupSafetyError(
                    "FlowTrack could not create the required automatic backup and has not "
                    "opened the database for writing."
                ) from error
    except BaseException:
        lease.release(identity)
        lock.release()
        raise
    logger.info("Opening dataset %s for writing", paths.root)
    return DatasetSession(paths, identity, False, engine, lease, lock)
