import json
import shutil
import sqlite3
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from flowtrack.application.startup import open_dataset
from flowtrack.infrastructure.backup import BackupManager, BackupReason, check_integrity
from flowtrack.infrastructure.conflicts import scan_dataset_conflicts
from flowtrack.infrastructure.dataset import DatasetPaths
from flowtrack.infrastructure.lease import LeaseState, LeaseStore
from flowtrack.persistence.database import create_database_engine


def _sqlite(path):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE sample (name TEXT)")
    connection.execute("INSERT INTO sample VALUES (?)", ("Café 東京 🚀",))
    connection.commit()
    connection.close()


def test_clean_scan_ignores_managed_paths_and_sidecars(tmp_path):
    paths = DatasetPaths(tmp_path)
    paths.initialise()
    _sqlite(paths.database)
    for name in ("flowtrack.db-wal", "flowtrack.db-shm", "flowtrack.db-journal",
                 ".flowtrack-session.json", ".flowtrack-restore.tmp", "unrelated.db"):
        (tmp_path / name).write_bytes(b"untouched")
    (paths.backups / "flowtrack (conflicted copy).db").write_bytes(b"backup")
    (paths.attachments / "flowtrack copy.db").write_bytes(b"attachment")

    assert not scan_dataset_conflicts(paths).has_conflicts


def test_multiple_valid_and_malformed_conflicts_are_reported_without_mutation(tmp_path):
    paths = DatasetPaths(tmp_path)
    valid = tmp_path / "flowtrack-PCNAME.db"
    malformed = tmp_path / "flowtrack (conflicted copy 2026).db"
    _sqlite(valid)
    malformed.write_bytes(b"not sqlite")
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (valid, malformed)}

    result = scan_dataset_conflicts(paths)

    assert [item.filename for item in result.candidates] == [malformed.name, valid.name]
    assert {item.filename: item.sqlite_valid for item in result.candidates} == {
        malformed.name: False, valid.name: True,
    }
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before}


@pytest.mark.parametrize("name", ["flowtrack copy.db", "flowtrack - Copy.db", "flowtrack (1).db",
                                  "flowtrack-conflicted-copy.db"])
def test_common_copy_names_are_suspicious(tmp_path, name):
    (tmp_path / name).write_bytes(b"preserve")
    assert [item.filename for item in scan_dataset_conflicts(DatasetPaths(tmp_path)).candidates] == [name]


def test_conflict_decision_precedes_lock_lease_and_migration(tmp_path):
    paths = DatasetPaths(tmp_path)
    candidate = tmp_path / "flowtrack copy.db"
    candidate.write_bytes(b"preserve")
    events = []

    class Lock:
        def __init__(self, _path):
            events.append("lock-created")
        def acquire(self):
            events.append("lock-acquired")
            return True
        def release(self):
            pass

    assert open_dataset(paths, lambda _state: pytest.fail("lease decision"),
                        decide_conflicts=lambda result: events.append("warning") or False,
                        lock_factory=Lock, migrate=lambda _path: events.append("migrate")) is None
    assert events == ["warning"]
    assert not paths.session_lease.exists()
    assert candidate.read_bytes() == b"preserve"

    session = open_dataset(paths, lambda _state: pytest.fail("lease decision"),
                           decide_conflicts=lambda _result: True, lock_factory=Lock,
                           migrate=lambda path: _sqlite(path))
    assert session is not None
    session.close()
    assert candidate.exists()  # It will be warned about again next launch.


def test_conservative_pragmas_survive_reopen_and_do_not_require_wal(tmp_path):
    path = tmp_path / "flowtrack.db"
    for _ in range(2):
        engine = create_database_engine(path)
        with engine.begin() as connection:
            assert connection.scalar(text("PRAGMA journal_mode")) == "delete"
            assert connection.scalar(text("PRAGMA synchronous")) == 2
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1
            connection.execute(text("CREATE TABLE IF NOT EXISTS durable (value TEXT)"))
            connection.execute(text("INSERT INTO durable VALUES ('kept')"))
        engine.dispose()
    assert not (tmp_path / "flowtrack.db-wal").exists()
    assert not (tmp_path / "flowtrack.db-shm").exists()
    assert check_integrity(path, full=True).ok


def test_closed_wal_database_is_safely_converted_without_data_loss(tmp_path):
    path = tmp_path / "flowtrack.db"
    connection = sqlite3.connect(path)
    assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    connection.execute("CREATE TABLE durable (value TEXT)")
    connection.execute("INSERT INTO durable VALUES ('committed')")
    connection.commit()
    connection.close()

    engine = create_database_engine(path)
    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA journal_mode")) == "delete"
        assert connection.scalar(text("SELECT value FROM durable")) == "committed"
    engine.dispose()


def test_backup_is_portable_standalone_sqlite_without_source_path(tmp_path):
    paths = DatasetPaths(tmp_path / "source")
    paths.initialise()
    _sqlite(paths.database)
    backup = BackupManager(paths).create(
        BackupReason.MANUAL, now=datetime(2026, 9, 3, 12, 34, 56, tzinfo=timezone.utc)
    )
    assert backup.path.name == "flowtrack-20260903-123456-manual.db"
    moved = tmp_path / "Windows-like portable folder" / "copied.db"
    moved.parent.mkdir()
    shutil.copy2(backup.path, moved)
    assert check_integrity(moved, full=True).ok
    connection = sqlite3.connect(moved)
    try:
        assert connection.execute("SELECT name FROM sample").fetchone()[0] == "Café 東京 🚀"
        values = [str(value) for row in connection.execute("SELECT * FROM sample") for value in row]
        assert not any(str(paths.root) in value for value in values)
    finally:
        connection.close()


@pytest.mark.parametrize("source_platform", ["Darwin", "Windows"])
def test_lease_json_from_either_platform_is_portable(tmp_path, source_platform):
    path = tmp_path / ".flowtrack-session.json"
    path.write_text(json.dumps({
        "instance_id": "portable-id",
        "machine_id": "opaque-machine-id",
        "platform": source_platform,
        "flowtrack_version": "0.1.0",
        "session_started_utc": "2026-09-03T12:00:00Z",
        "last_heartbeat_utc": "2026-09-03T12:00:00Z",
    }), encoding="utf-8")
    result = LeaseStore(path).evaluate(
        "portable-id", now=datetime(2026, 9, 3, 12, 1, tzinfo=timezone.utc)
    )
    assert result.state is LeaseState.OWNED_BY_THIS_INSTANCE
    assert result.lease is not None and result.lease.platform == source_platform
    assert "/" not in result.lease.machine_id and "\\" not in result.lease.machine_id
