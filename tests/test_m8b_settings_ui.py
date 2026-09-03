from datetime import datetime, timezone

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from flowtrack.infrastructure.backup import BackupInfo, BackupReason, IntegrityResult
from PySide6.QtWidgets import QDialog, QMessageBox

from flowtrack.ui.views.settings import ChangeDataLocationDialog, SettingsView


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


def test_settings_displays_active_location_and_change_action(application, tmp_path):
    view = SettingsView(tmp_path, Safety([]))
    assert view.data_location_label.text() == str(tmp_path)
    assert view.change_location_button.text() == "Change Data Location…"


def test_change_dialog_requires_explicit_mode_and_respects_read_only(application):
    writable = ChangeDataLocationDialog(move_enabled=True)
    assert writable.move_option.isChecked()
    assert writable.existing_option.isEnabled()
    read_only = ChangeDataLocationDialog(move_enabled=False)
    assert not read_only.move_option.isEnabled()
    assert read_only.existing_option.isChecked()


def test_confirmations_default_to_cancel_and_escape(application, tmp_path, monkeypatch):
    view = SettingsView(tmp_path, Safety([]))
    observed = []

    def cancel(dialog):
        observed.append({
            "accessible_name": dialog.accessibleName(),
            "text": dialog.text(),
            "affirmative": dialog.button(QMessageBox.StandardButton.Ok).text(),
            "default": dialog.defaultButton().text(),
            "escape": dialog.escapeButton().text(),
        })
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "exec", cancel)
    assert not view._confirm_move(tmp_path / "new")
    assert not view._confirm_existing(tmp_path / "old")
    move, existing = observed
    assert move["accessible_name"] == "Move FlowTrack Data?"
    assert "safely copy" in move["text"]
    assert str(tmp_path / "new") in move["text"]
    assert move["affirmative"] == "Move Data"
    assert existing["accessible_name"] == "Use Existing FlowTrack Data?"
    assert "switch to" in existing["text"]
    assert str(tmp_path / "old") in existing["text"]
    assert existing["affirmative"] == "Use This Data"
    assert all(item["default"] == "Cancel" and item["escape"] == "Cancel"
               for item in observed)
