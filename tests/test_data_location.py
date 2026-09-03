"""Safe data-location relocation and selection behavior."""

from pathlib import Path

import pytest

from flowtrack.application.data_location import DataLocationError, DatasetRelocationService
from flowtrack.infrastructure.backup import BackupManager, BackupReason
from flowtrack.infrastructure.dataset import DatasetPaths
from flowtrack.persistence.database import migrate_database
from flowtrack.application.startup import StartupChoice, open_dataset
from flowtrack.infrastructure.conflicts import ConflictScanResult


class Settings:
    def __init__(self, directory: Path) -> None:
        self.data_directory = directory


class Safety:
    read_only = False

    def __init__(self, paths: DatasetPaths) -> None:
        self.manager = BackupManager(paths)

    def create_manual_backup(self):
        return self.manager.create(BackupReason.MANUAL)


def dataset(root: Path) -> DatasetPaths:
    paths = DatasetPaths(root)
    paths.initialise()
    migrate_database(paths.database)
    return paths


@pytest.mark.parametrize("name", ["destination with spaces", "données-東京"])
def test_move_copies_only_durable_data_and_preserves_source(tmp_path, name):
    source = dataset(tmp_path / "source")
    backup = Safety(source).create_manual_backup().path
    source.session_lease.write_text("active")
    settings = Settings(source.root)
    service = DatasetRelocationService(source.root, settings, Safety(source))
    move = service.prepare_move(tmp_path / name)
    # These simulate remnants observed only after the clean session boundary;
    # relocation still copies from an explicit durable allow-list.
    for suffix in ("-wal", "-shm", "-journal"):
        source.database.with_name(source.database.name + suffix).write_text("transient")
    service.complete_move(move)

    target = DatasetPaths(tmp_path / name)
    assert source.database.exists()
    assert target.database.exists()
    assert (target.backups / backup.name).exists()
    assert not target.session_lease.exists()
    assert not any(target.database.with_name(target.database.name + suffix).exists()
                   for suffix in ("-wal", "-shm", "-journal"))
    assert settings.data_directory == target.root.resolve()


def test_move_rejects_existing_database_and_same_path(tmp_path):
    source = dataset(tmp_path / "source")
    service = DatasetRelocationService(source.root, Settings(source.root), Safety(source))
    occupied = tmp_path / "occupied"; occupied.mkdir(); (occupied / "flowtrack.db").write_text("x")
    with pytest.raises(DataLocationError, match="already contains"):
        service.validate_move_destination(occupied)
    with pytest.raises(DataLocationError, match="already the current"):
        service.validate_move_destination(source.root / ".." / "source")


def test_invalid_destination_and_copy_failure_never_adopt_or_delete_source(tmp_path, monkeypatch):
    source = dataset(tmp_path / "source")
    settings = Settings(source.root)
    service = DatasetRelocationService(source.root, settings, Safety(source))
    invalid = tmp_path / "file"; invalid.write_text("not a directory")
    with pytest.raises(DataLocationError, match="not a folder"):
        service.validate_move_destination(invalid)
    move = service.prepare_move(tmp_path / "target")
    monkeypatch.setattr("flowtrack.application.data_location.shutil.copy2",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(DataLocationError, match="could not safely copy"):
        service.complete_move(move)
    assert settings.data_directory == source.root
    assert source.database.exists()
    assert not (tmp_path / "target" / "flowtrack.db").exists()


def test_failed_copied_integrity_does_not_adopt(tmp_path, monkeypatch):
    source = dataset(tmp_path / "source")
    settings = Settings(source.root)
    service = DatasetRelocationService(source.root, settings, Safety(source))
    move = service.prepare_move(tmp_path / "target")
    monkeypatch.setattr(service, "_validate_database",
                        lambda _path: (_ for _ in ()).throw(DataLocationError("bad copy")))
    with pytest.raises(DataLocationError, match="bad copy"):
        service.complete_move(move)
    assert settings.data_directory == source.root
    assert source.database.exists()


def test_existing_selection_is_read_only_and_requires_flowtrack_database(tmp_path):
    current = dataset(tmp_path / "current")
    existing = dataset(tmp_path / "existing")
    settings = Settings(current.root)
    service = DatasetRelocationService(current.root, settings, None)
    before = existing.database.read_bytes(), existing.database.stat().st_mtime_ns
    assert service.validate_existing(existing.root) == existing.root.resolve()
    after = existing.database.read_bytes(), existing.database.stat().st_mtime_ns
    assert after == before
    assert settings.data_directory == current.root
    service.adopt_existing(existing.root)
    assert settings.data_directory == existing.root.resolve()
    empty = tmp_path / "empty"; empty.mkdir()
    with pytest.raises(DataLocationError, match="does not contain"):
        service.validate_existing(empty)


def test_corrupt_existing_database_is_rejected(tmp_path):
    current = dataset(tmp_path / "current")
    corrupt = tmp_path / "corrupt"; corrupt.mkdir(); (corrupt / "flowtrack.db").write_text("no")
    settings = Settings(current.root)
    with pytest.raises(DataLocationError, match="integrity"):
        DatasetRelocationService(current.root, settings, None).validate_existing(corrupt)
    assert settings.data_directory == current.root


def test_changed_locations_still_use_normal_startup_safety(tmp_path):
    """Selection creates no trusted shortcut around open_dataset on restart."""
    current = dataset(tmp_path / "current")
    selected = dataset(tmp_path / "selected")
    settings = Settings(current.root)
    service = DatasetRelocationService(current.root, settings, Safety(current))
    service.adopt_existing(selected.root)

    conflict_scans = []
    session = open_dataset(
        DatasetPaths(settings.data_directory), lambda _state: StartupChoice.CANCEL,
        conflict_scanner=lambda paths: (
            conflict_scans.append(paths.root),
            ConflictScanResult(paths.database, ()),
        )[1],
    )
    assert session is not None
    assert conflict_scans == [selected.root.resolve()]
    assert session.lock is not None
    assert session.paths.session_lease.exists()
    session.close()
    assert not session.paths.session_lease.exists()
