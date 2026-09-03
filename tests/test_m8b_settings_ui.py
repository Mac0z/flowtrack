from datetime import datetime, timezone

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from flowtrack.infrastructure.backup import BackupInfo, BackupReason, IntegrityResult
from flowtrack.ui.views.settings import SettingsView


class Safety:
    def __init__(self, backups, read_only=False):
        self.backups = backups; self.read_only = read_only
    def list_backups(self, *, validate=True): return self.backups


def info(tmp_path, day, valid=True):
    return BackupInfo(tmp_path / f"{day}.db", datetime(2026, 9, day, tzinfo=timezone.utc),
                      BackupReason.MANUAL, day, IntegrityResult(valid, ("ok",)))


def test_settings_lists_backups_and_requires_valid_selection(application, tmp_path):
    view = SettingsView(tmp_path, Safety([info(tmp_path, 3), info(tmp_path, 2, False)]))
    assert view.backup_table.rowCount() == 2
    assert not view.restore_button.isEnabled()
    view.backup_table.selectRow(0)
    assert view.restore_button.isEnabled()
    view.backup_table.selectRow(1)
    assert not view.restore_button.isEnabled()


def test_settings_disables_mutating_actions_in_read_only_mode(application, tmp_path):
    view = SettingsView(tmp_path, Safety([info(tmp_path, 3)], read_only=True))
    view.backup_table.selectRow(0)
    assert not view.backup_now_button.isEnabled()
    assert not view.restore_button.isEnabled()
