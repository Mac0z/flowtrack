"""SQLite-native backup, integrity, retention, and restore primitives."""

from __future__ import annotations

import logging
import os
import re
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from flowtrack.infrastructure.dataset import DatasetPaths

logger = logging.getLogger(__name__)
_BACKUP_RE = re.compile(
    r"^flowtrack-(\d{8})-(\d{6})-(daily|migration|manual|pre-restore)(?:-(\d+))?\.db$"
)


class BackupReason(Enum):
    DAILY = "daily"
    MIGRATION = "migration"
    MANUAL = "manual"
    PRE_RESTORE = "pre-restore"


@dataclass(frozen=True)
class IntegrityResult:
    ok: bool
    messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    timestamp: datetime
    reason: BackupReason
    size: int
    integrity: IntegrityResult | None = None


class BackupError(RuntimeError):
    """A safe, user-presentable data-safety failure."""


def check_integrity(path: Path, *, full: bool = False) -> IntegrityResult:
    """Check a database without depending on FlowTrack's ORM schema."""
    if not path.is_file() or path.stat().st_size == 0:
        return IntegrityResult(False, ("The database file is missing or empty.",))
    connection: sqlite3.Connection | None = None
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        pragma = "integrity_check" if full else "quick_check"
        messages = tuple(str(row[0]) for row in connection.execute(f"PRAGMA {pragma}"))
        result = IntegrityResult(messages == ("ok",), messages)
        logger.info("SQLite %s for %s: %s", pragma, path, "ok" if result.ok else "failed")
        return result
    except (OSError, sqlite3.Error) as error:
        logger.warning("SQLite integrity check failed for %s: %s", path, error)
        return IntegrityResult(False, ("The file could not be validated as a SQLite database.",))
    finally:
        if connection is not None:
            connection.close()


class BackupManager:
    def __init__(self, paths: DatasetPaths, *, clock: Callable[[], datetime] | None = None) -> None:
        self.paths = paths
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def list_backups(self, *, validate: bool = False) -> list[BackupInfo]:
        if not self.paths.backups.exists():
            return []
        items: list[BackupInfo] = []
        for path in self.paths.backups.iterdir():
            parsed = self._parse(path)
            if parsed is None:
                continue
            timestamp, reason = parsed
            integrity = check_integrity(path, full=True) if validate else None
            items.append(BackupInfo(path, timestamp, reason, path.stat().st_size, integrity))
        return sorted(items, key=lambda item: (item.timestamp, item.path.name), reverse=True)

    def create(self, reason: BackupReason, *, now: datetime | None = None) -> BackupInfo:
        """Create and fully validate a standalone backup using SQLite's backup API."""
        moment = (now or self._clock()).astimezone(timezone.utc)
        self.paths.backups.mkdir(parents=True, exist_ok=True)
        destination = self._unique_path(moment, reason)
        temporary = destination.with_name(f".{destination.name}.tmp")
        logger.info("Backup requested (%s): %s", reason.value, destination)
        try:
            source_uri = f"{self.paths.database.resolve().as_uri()}?mode=ro"
            with closing(sqlite3.connect(source_uri, uri=True)) as source, closing(
                sqlite3.connect(temporary)
            ) as target:
                source.backup(target)
            result = check_integrity(temporary, full=True)
            if not result.ok:
                raise BackupError("FlowTrack could not validate the new backup.")
            self._sync_file(temporary)
            os.replace(temporary, destination)
            info = BackupInfo(destination, moment, reason, destination.stat().st_size, result)
            logger.info("Backup completed (%s): %s", reason.value, destination)
            return info
        except BackupError:
            logger.exception("Backup failed (%s)", reason.value)
            raise
        except (OSError, sqlite3.Error) as error:
            logger.exception("Backup failed (%s): %s", reason.value, error)
            raise BackupError("FlowTrack could not create a safe backup.") from error
        finally:
            self._remove_temporary(temporary)

    def create_daily_if_needed(self, *, now: datetime | None = None) -> BackupInfo | None:
        """Back up once per UTC day when the DB is newer than the newest backup."""
        moment = (now or self._clock()).astimezone(timezone.utc)
        backups = self.list_backups()
        if any(item.reason is BackupReason.DAILY and item.timestamp.date() == moment.date()
               for item in backups):
            return None
        if backups and self.paths.database.stat().st_mtime_ns <= max(
            item.path.stat().st_mtime_ns for item in backups
        ):
            return None
        info = self.create(BackupReason.DAILY, now=moment)
        self.apply_daily_retention()
        return info

    def apply_daily_retention(self, keep: int = 30) -> None:
        daily = [item for item in self.list_backups() if item.reason is BackupReason.DAILY]
        for item in daily[keep:]:
            try:
                item.path.unlink()
                logger.info("Removed expired daily backup: %s", item.path)
            except OSError:
                logger.exception("Could not remove expired daily backup: %s", item.path)

    def restore(self, source: Path, *, close_connections: Callable[[], None]) -> BackupInfo:
        """Validate, preserve, replace atomically, and validate again."""
        source = source.resolve()
        managed = {item.path.resolve() for item in self.list_backups()}
        logger.info("Restore source selected: %s", source)
        if source not in managed or not check_integrity(source, full=True).ok:
            raise BackupError("The selected backup is invalid and was not restored.")
        safety = self.create(BackupReason.PRE_RESTORE)
        candidate = self.paths.database.with_name(".flowtrack-restore.tmp")
        close_connections()
        try:
            shutil.copyfile(source, candidate)
            if not check_integrity(candidate, full=True).ok:
                raise BackupError("The selected backup could not be prepared safely.")
            self._sync_file(candidate)
            os.replace(candidate, self.paths.database)
            for suffix in ("-wal", "-shm", "-journal"):
                self.paths.database.with_name(self.paths.database.name + suffix).unlink(missing_ok=True)
            if not check_integrity(self.paths.database, full=True).ok:
                self._adopt_safety_copy(safety.path)
                raise BackupError("Restore validation failed; the original database was recovered.")
            logger.info("Restore completed; restart required: %s", source)
            return safety
        except BackupError:
            logger.exception("Restore failed")
            raise
        except OSError as error:
            logger.exception("Restore failed: %s", error)
            if not self.paths.database.exists():
                self._adopt_safety_copy(safety.path)
            raise BackupError("FlowTrack could not restore the backup safely.") from error
        finally:
            self._remove_temporary(candidate)

    def _adopt_safety_copy(self, safety: Path) -> None:
        candidate = self.paths.database.with_name(".flowtrack-rollback.tmp")
        shutil.copyfile(safety, candidate)
        os.replace(candidate, self.paths.database)
        logger.warning("Recovered current database from pre-restore backup: %s", safety)

    def _unique_path(self, moment: datetime, reason: BackupReason) -> Path:
        stem = f"flowtrack-{moment:%Y%m%d-%H%M%S}-{reason.value}"
        candidate = self.paths.backups / f"{stem}.db"
        counter = 1
        while candidate.exists() or candidate.with_name(f".{candidate.name}.tmp").exists():
            candidate = self.paths.backups / f"{stem}-{counter}.db"
            counter += 1
        return candidate

    @staticmethod
    def _sync_file(path: Path) -> None:
        """Ask the OS to flush a completed candidate before atomic adoption."""
        # Windows' fsync implementation requires a writable file descriptor.
        with path.open("r+b") as stream:
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _remove_temporary(path: Path) -> None:
        """Best-effort cleanup that cannot replace the operation's real error."""
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove temporary database file: %s", path, exc_info=True)

    @staticmethod
    def _parse(path: Path) -> tuple[datetime, BackupReason] | None:
        match = _BACKUP_RE.fullmatch(path.name)
        if match is None or not path.is_file():
            return None
        timestamp = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        )
        return timestamp, BackupReason(match.group(3))
