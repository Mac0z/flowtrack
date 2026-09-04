import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QSettings

from flowtrack.infrastructure.settings import ApplicationSettings


def test_performance_diagnostics_preference_defaults_off_and_persists(tmp_path):
    path = tmp_path / "settings.ini"
    settings = ApplicationSettings(QSettings(str(path), QSettings.Format.IniFormat))
    assert settings.performance_diagnostics_enabled is False
    settings.performance_diagnostics_enabled = True
    restored = ApplicationSettings(QSettings(str(path), QSettings.Format.IniFormat))
    assert restored.performance_diagnostics_enabled is True
