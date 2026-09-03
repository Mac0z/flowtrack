import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from flowtrack.application.data_safety import DataSafetyService, ReadOnlySafetyError
from flowtrack.application.startup import StartupChoice, StartupSafetyError, open_dataset
from flowtrack.infrastructure.backup import (
    BackupError, BackupManager, BackupReason, check_integrity,
)
from flowtrack.infrastructure.dataset import DatasetPaths
from flowtrack.persistence.database import migrate_database, migration_required, migration_status


NOW = datetime(2026, 9, 3, 14, 15, tzinfo=timezone.utc)


def database(path, value="current"):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sample(value TEXT)")
        connection.execute("INSERT INTO sample VALUES (?)", (value,))


def value(path):
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT value FROM sample").fetchone()[0]


def test_backup_is_standalone_valid_contains_data_and_never_overwrites(tmp_path):
    paths = DatasetPaths(tmp_path); paths.initialise(); database(paths.database)
    manager = BackupManager(paths)
    first = manager.create(BackupReason.MANUAL, now=NOW)
    second = manager.create(BackupReason.MANUAL, now=NOW)
    assert first.path.name == "flowtrack-20260903-141500-manual.db"
    assert second.path.name == "flowtrack-20260903-141500-manual-1.db"
    assert value(first.path) == "current" and check_integrity(first.path, full=True).ok
    assert not list(paths.backups.glob(".*.tmp"))


def test_failed_backup_removes_partial_temporary_file(tmp_path, monkeypatch):
    paths = DatasetPaths(tmp_path); paths.initialise(); database(paths.database)
    monkeypatch.setattr("flowtrack.infrastructure.backup.check_integrity",
                        lambda *_args, **_kwargs: type("Result", (), {"ok": False})())
    with pytest.raises(BackupError):
        BackupManager(paths).create(BackupReason.MANUAL, now=NOW)
    assert list(paths.backups.iterdir()) == []


def test_integrity_failure_is_structured_and_safe(tmp_path):
    malformed = tmp_path / "bad.db"; malformed.write_bytes(b"not sqlite")
    result = check_integrity(malformed, full=True)
    assert not result.ok
    assert result.messages == ("The file could not be validated as a SQLite database.",)


def test_daily_policy_uses_day_and_changes(tmp_path):
    paths = DatasetPaths(tmp_path); paths.initialise(); database(paths.database)
    manager = BackupManager(paths)
    first = manager.create_daily_if_needed(now=NOW)
    assert first is not None
    assert manager.create_daily_if_needed(now=NOW + timedelta(hours=1)) is None
    # A later day without a database modification creates no redundant backup.
    assert manager.create_daily_if_needed(now=NOW + timedelta(days=1)) is None
    future = first.path.stat().st_mtime_ns + 1_000_000_000
    os.utime(paths.database, ns=(future, future))
    assert manager.create_daily_if_needed(now=NOW + timedelta(days=1)) is not None


def test_retention_only_removes_old_managed_daily_backups(tmp_path):
    paths = DatasetPaths(tmp_path); paths.initialise(); database(paths.database)
    manager = BackupManager(paths)
    for offset in range(32):
        manager.create(BackupReason.DAILY, now=NOW + timedelta(days=offset))
    manual = manager.create(BackupReason.MANUAL, now=NOW)
    migration = manager.create(BackupReason.MIGRATION, now=NOW)
    safety = manager.create(BackupReason.PRE_RESTORE, now=NOW)
    unrelated = paths.backups / "notes.txt"; unrelated.write_text("keep")
    manager.apply_daily_retention()
    assert len([item for item in manager.list_backups() if item.reason is BackupReason.DAILY]) == 30
    assert all(path.exists() for path in (manual.path, migration.path, safety.path, unrelated))


def test_restore_preserves_current_and_requests_connection_close(tmp_path):
    paths = DatasetPaths(tmp_path); paths.initialise(); database(paths.database, "old")
    manager = BackupManager(paths)
    source = manager.create(BackupReason.MANUAL, now=NOW)
    paths.database.unlink(); database(paths.database, "new")
    closed = []
    safety = manager.restore(source.path, close_connections=lambda: closed.append(True))
    assert closed == [True]
    assert value(paths.database) == "old" and value(safety.path) == "new"
    assert source.path.exists() and safety.reason is BackupReason.PRE_RESTORE


def test_invalid_restore_never_touches_current_or_closes_connections(tmp_path):
    paths = DatasetPaths(tmp_path); paths.initialise(); database(paths.database)
    bad = paths.backups / "flowtrack-20260903-141500-manual.db"; bad.write_bytes(b"bad")
    closed = []
    with pytest.raises(BackupError):
        BackupManager(paths).restore(bad, close_connections=lambda: closed.append(True))
    assert value(paths.database) == "current" and closed == []


def test_manual_backup_is_rejected_in_read_only_mode(tmp_path):
    paths = DatasetPaths(tmp_path); paths.initialise(); database(paths.database)
    service = DataSafetyService(BackupManager(paths), read_only=True,
                                close_connections=lambda: None)
    with pytest.raises(ReadOnlySafetyError):
        service.create_manual_backup()


def test_migration_detection_distinguishes_new_current_and_older_database(tmp_path):
    new = tmp_path / "new.db"
    assert migration_status(new)[0] is None and not migration_required(new)
    migrate_database(new)
    current, head = migration_status(new)
    assert current == head and not migration_required(new)
    with sqlite3.connect(new) as connection:
        connection.execute("UPDATE alembic_version SET version_num='older_revision'")
    assert migration_required(new)


def test_startup_creates_migration_backup_before_migrating(tmp_path):
    paths = DatasetPaths(tmp_path); paths.initialise(); database(paths.database)
    events = []

    class Manager:
        def __init__(self, _paths): pass
        def create(self, reason, *, now=None):
            events.append(reason.value)
        def create_daily_if_needed(self, *, now=None):
            events.append("daily")

    def migrate(_path):
        events.append("migrate")

    session = open_dataset(paths, lambda _state: StartupChoice.CANCEL, migrate=migrate,
                           needs_migration=lambda _path: True,
                           backup_manager_factory=Manager)
    assert events[:2] == ["migration", "migrate"]
    session.close()


def test_startup_aborts_migration_when_required_backup_fails(tmp_path):
    paths = DatasetPaths(tmp_path); paths.initialise(); database(paths.database)
    migrated = []

    class Manager:
        def __init__(self, _paths): pass
        def create(self, _reason, *, now=None): raise BackupError("failure")

    with pytest.raises(StartupSafetyError):
        open_dataset(paths, lambda _state: StartupChoice.CANCEL,
                     migrate=lambda _path: migrated.append(True),
                     needs_migration=lambda _path: True,
                     backup_manager_factory=Manager)
    assert migrated == []
    assert not paths.session_lease.exists()


def test_restore_aborts_before_close_when_pre_restore_backup_fails(tmp_path, monkeypatch):
    paths = DatasetPaths(tmp_path); paths.initialise(); database(paths.database)
    manager = BackupManager(paths); source = manager.create(BackupReason.MANUAL, now=NOW)
    original = value(paths.database); closed = []
    monkeypatch.setattr(manager, "create", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        BackupError("failure")
    ))
    with pytest.raises(BackupError):
        manager.restore(source.path, close_connections=lambda: closed.append(True))
    assert value(paths.database) == original and closed == []
