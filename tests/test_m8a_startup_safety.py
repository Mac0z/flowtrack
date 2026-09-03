from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from flowtrack.application.startup import StartupChoice, open_dataset
from flowtrack.infrastructure.dataset import DatasetPaths, resolve_saved_or_legacy_dataset
from flowtrack.infrastructure.lease import LeaseState, LeaseStore, SessionLease
from flowtrack.infrastructure.locking import DatasetLock
from flowtrack.persistence.database import create_database_engine


NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)


class FakeSettings:
    data_directory = None


def test_legacy_database_is_adopted_without_being_moved(tmp_path):
    legacy = tmp_path / "legacy" / "flowtrack.db"
    legacy.parent.mkdir()
    legacy.write_bytes(b"important existing data")
    settings = FakeSettings()
    paths = resolve_saved_or_legacy_dataset(settings, legacy)
    assert paths is not None and paths.database == legacy
    assert settings.data_directory == legacy.parent
    assert legacy.read_bytes() == b"important existing data"


def test_saved_directory_wins_without_touching_legacy_database(tmp_path):
    selected = tmp_path / "selected"
    legacy = tmp_path / "legacy" / "flowtrack.db"
    legacy.parent.mkdir()
    legacy.write_bytes(b"legacy")
    settings = FakeSettings()
    settings.data_directory = selected
    assert resolve_saved_or_legacy_dataset(settings, legacy).root == selected
    assert legacy.read_bytes() == b"legacy"


def test_dataset_layout_is_deterministic(tmp_path):
    paths = DatasetPaths(tmp_path / "chosen")
    assert paths.database == paths.root / "flowtrack.db"
    assert paths.session_lease == paths.root / ".flowtrack-session.json"
    paths.initialise()
    assert paths.backups.is_dir()
    assert paths.attachments.is_dir()


def test_local_lock_excludes_same_dataset_and_not_different_datasets(tmp_path):
    state = tmp_path / "local-state"
    first = DatasetLock(tmp_path / "one", state_directory=state)
    second = DatasetLock(tmp_path / "one", state_directory=state)
    different = DatasetLock(tmp_path / "two", state_directory=state)
    assert first.acquire()
    assert not second.acquire()
    assert different.acquire()
    first.release()
    assert second.acquire()
    first.release()  # cleanup is idempotent
    second.release()
    different.release()


def test_lease_lifecycle_and_states(tmp_path):
    store = LeaseStore(tmp_path / ".flowtrack-session.json")
    assert store.evaluate("mine", now=NOW).state is LeaseState.ABSENT
    lease = store.claim("mine", now=NOW)
    assert SessionLease(**lease.__dict__).instance_id == "mine"
    assert store.evaluate("mine", now=NOW).state is LeaseState.OWNED_BY_THIS_INSTANCE
    assert store.evaluate("other", now=NOW).state is LeaseState.ACTIVE_OTHER_INSTANCE
    assert store.evaluate("other", now=NOW + timedelta(minutes=4)).state is LeaseState.STALE_OTHER_INSTANCE
    assert store.heartbeat("mine", now=NOW + timedelta(seconds=30))
    assert store.evaluate("mine", now=NOW + timedelta(seconds=30)).lease.last_heartbeat_utc.endswith("Z")
    assert not store.release("other")
    assert store.path.exists()
    assert store.release("mine")


def test_malformed_lease_is_conservative(tmp_path):
    path = tmp_path / ".flowtrack-session.json"
    path.write_text("not json", encoding="utf-8")
    assert LeaseStore(path).evaluate("mine").state is LeaseState.MALFORMED


@pytest.mark.parametrize("state_age", [timedelta(0), timedelta(minutes=4)])
def test_foreign_lease_never_silently_enters_write_mode(tmp_path, state_age):
    paths = DatasetPaths(tmp_path / "data")
    paths.initialise()
    LeaseStore(paths.session_lease).claim("foreign", now=NOW - state_age)
    decisions = []

    def decide(state):
        decisions.append(state)
        return StartupChoice.CANCEL

    session = open_dataset(paths, decide, instance_id="mine", migrate=lambda _path: None, now=NOW)
    assert session is None
    assert decisions == [LeaseState.ACTIVE_OTHER_INSTANCE if not state_age else LeaseState.STALE_OTHER_INSTANCE]


def test_write_ownership_precedes_migration_and_cleanup_is_safe(tmp_path):
    paths = DatasetPaths(tmp_path / "data")

    def migrate(_path):
        assert paths.session_lease.exists()

    session = open_dataset(paths, lambda _state: StartupChoice.CANCEL,
                           instance_id="mine", migrate=migrate)
    assert session is not None and not session.read_only
    assert paths.session_lease.exists()
    session.close()
    session.close()
    assert not paths.session_lease.exists()


def test_read_only_sqlite_allows_queries_and_rejects_writes(tmp_path):
    path = tmp_path / "flowtrack.db"
    writable = create_database_engine(path)
    with writable.begin() as connection:
        connection.execute(text("CREATE TABLE sample (value INTEGER)"))
        connection.execute(text("INSERT INTO sample VALUES (1)"))
    writable.dispose()
    readonly = create_database_engine(path, read_only=True)
    with readonly.connect() as connection:
        assert connection.scalar(text("SELECT value FROM sample")) == 1
        with pytest.raises(Exception):
            connection.execute(text("INSERT INTO sample VALUES (2)"))
    readonly.dispose()


def test_read_only_startup_does_not_migrate_or_claim_lease(tmp_path):
    paths = DatasetPaths(tmp_path / "data")
    paths.initialise()
    create_database_engine(paths.database).dispose()
    LeaseStore(paths.session_lease).claim("foreign", now=NOW)
    migrated = False

    def migrate(_path):
        nonlocal migrated
        migrated = True

    session = open_dataset(paths, lambda _state: StartupChoice.READ_ONLY,
                           instance_id="mine", migrate=migrate, now=NOW)
    assert session is not None and session.read_only
    assert not migrated
    assert LeaseStore(paths.session_lease).evaluate("foreign").state is LeaseState.OWNED_BY_THIS_INSTANCE
    session.close()
    assert paths.session_lease.exists()
