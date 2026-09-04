import importlib.util
import sys
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

_AUDIT_PATH = Path(__file__).parents[1] / "packaging" / "check_macos_architectures.py"
_AUDIT_SPEC = importlib.util.spec_from_file_location("macos_architecture_audit", _AUDIT_PATH)
assert _AUDIT_SPEC is not None and _AUDIT_SPEC.loader is not None
macos_audit = importlib.util.module_from_spec(_AUDIT_SPEC)
sys.modules[_AUDIT_SPEC.name] = macos_audit
_AUDIT_SPEC.loader.exec_module(macos_audit)


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


def test_macos_packaging_disables_sqlalchemy_native_extensions() -> None:
    workflow = (
        Path(__file__).parents[1] / ".github" / "workflows" / "package.yml"
    ).read_text(encoding="utf-8")
    macos_job = workflow.split("  macos:", maxsplit=1)[1]

    assert 'DISABLE_SQLALCHEMY_CEXT: "1"' in macos_job
    assert "--no-binary SQLAlchemy" in macos_job
    assert macos_job.index("Audit universal2 runtime dependencies") < macos_job.index(
        "Build universal2 application"
    )


def test_macos_packaging_disables_markupsafe_speedups() -> None:
    workflow = (
        Path(__file__).parents[1] / ".github" / "workflows" / "package.yml"
    ).read_text(encoding="utf-8")
    macos_job = workflow.split("  macos:", maxsplit=1)[1]

    assert 'MARKUPSAFE_NO_SPEEDUPS: "1"' in macos_job
    assert "--no-binary MarkupSafe" in macos_job
    assert "import markupsafe" in macos_job
    assert "from mako.template import Template" in macos_job
    assert "packaging/check_macos_architectures.py" in macos_job
    assert macos_job.index("Audit universal2 runtime dependencies") < macos_job.index(
        "packaging/build.py"
    )


def _fake_macos_tools(file_architectures: dict[Path, str | None]):
    """Simulate macOS tools using the identity of the inspected file."""

    def run(command: tuple[str, ...]) -> str:
        path = Path(command[-1])
        assert path in file_architectures, f"Unexpected file inspection: {path}"
        architectures = file_architectures[path]
        if command[:2] == ("file", "-b"):
            if architectures is None:
                return f"{path}: ASCII text"
            return f"{path}: Mach-O 64-bit bundle {architectures}"
        assert command[:2] == ("lipo", "-archs")
        assert architectures is not None, f"lipo called for non-Mach-O file: {path}"
        return architectures

    return run


def test_architecture_audit_accepts_universal2(tmp_path) -> None:
    binary = tmp_path / "native.so"
    binary.touch()
    result = macos_audit.inspect_file(
        binary,
        "Example",
        run_command=_fake_macos_tools({binary: "x86_64 arm64"}),
    )
    assert result.classification == "universal2"


def test_architecture_audit_finds_extensionless_framework_binary(
    tmp_path, monkeypatch
) -> None:
    binary = tmp_path / "QtCore.framework" / "Versions" / "A" / "QtCore"
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.setattr(macos_audit.os, "access", lambda path, mode: path == binary)
    assert binary in macos_audit.candidate_files(tmp_path)
    results, incompatible = macos_audit.audit_roots(
        [("PySide6", tmp_path)],
        run_command=_fake_macos_tools({binary: "x86_64 arm64"}),
    )
    assert results["PySide6"][0].classification == "universal2"
    assert incompatible == []


@pytest.mark.parametrize(
    ("architectures", "classification"),
    [("arm64", "arm64-only"), ("x86_64", "x86_64-only")],
)
def test_architecture_audit_rejects_thin_binary(
    tmp_path, architectures, classification
) -> None:
    binary = tmp_path / "native.so"
    binary.touch()
    results, incompatible = macos_audit.audit_roots(
        [("Example", tmp_path)],
        run_command=_fake_macos_tools({binary: architectures}),
    )
    assert results["Example"][0].classification == classification
    assert incompatible == results["Example"]
    diagnostic = (
        f"package={incompatible[0].package} path={incompatible[0].path} "
        f"architectures={' '.join(incompatible[0].architectures)}"
    )
    assert "package=Example" in diagnostic
    assert str(binary) in diagnostic
    assert f"architectures={architectures}" in diagnostic


def test_architecture_audit_ignores_pure_python_package(tmp_path, monkeypatch) -> None:
    module = tmp_path / "module.py"
    module.write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(macos_audit.os, "access", lambda path, mode: False)
    results, incompatible = macos_audit.audit_roots(
        [("Pure", tmp_path)], run_command=_fake_macos_tools({module: None})
    )
    assert results == {"Pure": []}
    assert incompatible == []
    assert macos_audit.format_status(results["Pure"]) == "pure Python / OK"


def test_architecture_audit_ignores_non_macho_candidate(tmp_path) -> None:
    candidate = tmp_path / "data.so"
    candidate.write_text("not a binary", encoding="utf-8")
    results, incompatible = macos_audit.audit_roots(
        [("Data", tmp_path)], run_command=_fake_macos_tools({candidate: None})
    )
    assert results["Data"][0].classification == "non-Mach-O / not applicable"
    assert incompatible == []
