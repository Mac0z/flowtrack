from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

from flowtrack import __version__
from flowtrack.infrastructure import identity
from flowtrack.infrastructure.identity import APPLICATION_NAME, ORGANIZATION_NAME
from flowtrack.infrastructure.packaging_smoke import run_packaging_smoke
from flowtrack.infrastructure.paths import application_data_directory, log_directory
from flowtrack.infrastructure.resources import migration_directory
from flowtrack.persistence.database import migration_config


def test_version_comes_from_distribution_metadata() -> None:
    assert __version__ == "0.1.0"


def test_source_tree_without_metadata_reads_project_version(monkeypatch) -> None:
    def missing(_name: str) -> str:
        raise identity.PackageNotFoundError

    monkeypatch.setattr(identity, "version", missing)
    assert identity.application_version() == "0.1.0"


def test_migration_resources_are_complete_and_used_by_alembic() -> None:
    migrations = migration_directory()
    assert (migrations / "env.py").is_file()
    assert (migrations / "script.py.mako").is_file()
    assert any((migrations / "versions").glob("*.py"))
    assert Path(migration_config().get_main_option("script_location")) == migrations


def test_application_identity_is_stable() -> None:
    QCoreApplication.setOrganizationName(ORGANIZATION_NAME)
    QCoreApplication.setApplicationName(APPLICATION_NAME)
    QCoreApplication.setApplicationVersion(__version__)
    assert QCoreApplication.organizationName() == ORGANIZATION_NAME
    assert QCoreApplication.applicationName() == APPLICATION_NAME
    assert QCoreApplication.applicationVersion() == __version__


def test_packaging_smoke_creates_no_persistent_dataset(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    run_packaging_smoke()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("platform_name", ["darwin", "win32"])
def test_runtime_files_remain_external_to_frozen_executable(
    tmp_path, monkeypatch, platform_name
) -> None:
    bundle = tmp_path / "read-only-install" / "FlowTrack.exe"
    monkeypatch.setattr("sys.executable", str(bundle))
    home = tmp_path / "user"
    environment = {"LOCALAPPDATA": str(home / "Local")}
    data = application_data_directory(
        platform_name=platform_name, environment=environment, home=home
    )
    assert bundle.parent not in data.parents
    assert bundle.parent not in log_directory(
        platform_name=platform_name, environment=environment, home=home
    ).parents
