"""Data-location, backup, and restore settings."""

from pathlib import Path
from collections.abc import Callable

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHeaderView, QLabel,
    QMessageBox, QPushButton, QRadioButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from flowtrack.application.data_location import (
    DataLocationError, DatasetRelocationService, PreparedMove,
)
from flowtrack.application.data_safety import DataSafetyService
from flowtrack.infrastructure.backup import BackupError, BackupInfo
from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.infrastructure.performance import PerformanceDiagnostics


class ChangeDataLocationDialog(QDialog):
    """Explicit choice between copying current data and selecting existing data."""

    def __init__(self, *, move_enabled: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Change Data Location")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Change Data Location"))
        self.move_option = QRadioButton("Move my current FlowTrack data")
        self.move_option.setObjectName("moveCurrentDataOption")
        self.move_option.setEnabled(move_enabled)
        layout.addWidget(self.move_option)
        move_detail = QLabel("Safely copy this FlowTrack data to another folder.")
        move_detail.setObjectName("mutedText"); layout.addWidget(move_detail)
        self.existing_option = QRadioButton("Use an existing FlowTrack data folder")
        self.existing_option.setObjectName("useExistingDataOption")
        layout.addWidget(self.existing_option)
        existing_detail = QLabel("Switch to FlowTrack data already stored elsewhere.")
        existing_detail.setObjectName("mutedText"); layout.addWidget(existing_detail)
        (self.move_option if move_enabled else self.existing_option).setChecked(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continue")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def move_selected(self) -> bool:
        return self.move_option.isChecked()


class SettingsView(QWidget):
    restart_requested = Signal()

    def __init__(self, data_directory: Path,
                 data_safety: DataSafetyService | None = None, *,
                 settings: ApplicationSettings | None = None,
                 performance: PerformanceDiagnostics | None = None,
                 commit_change: Callable[[PreparedMove | None, Path | None], None] | None = None) -> None:
        super().__init__()
        self.data_safety = data_safety
        self.data_directory = Path(data_directory)
        self.settings = settings or ApplicationSettings()
        self.performance = performance or PerformanceDiagnostics(False)
        self.relocation = DatasetRelocationService(
            self.data_directory, self.settings, self.data_safety
        )
        self._commit_change = commit_change
        self._backups: list[BackupInfo] = []
        layout = QVBoxLayout(self)
        title = QLabel("Settings"); title.setObjectName("pageTitle"); layout.addWidget(title)
        layout.addWidget(QLabel("Data Location"))
        self.data_location_label = QLabel(str(data_directory))
        self.data_location_label.setObjectName("mutedText")
        layout.addWidget(self.data_location_label)
        self.open_folder_button = QPushButton("Open Data Folder")
        self.open_folder_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_directory)))
        )
        layout.addWidget(self.open_folder_button)
        self.change_location_button = QPushButton("Change Data Location…")
        self.change_location_button.setObjectName("changeDataLocationButton")
        self.change_location_button.clicked.connect(self._change_data_location)
        layout.addWidget(self.change_location_button)
        layout.addWidget(QLabel("Backups"))
        self.last_daily_label = QLabel("Last automatic backup: None")
        self.last_daily_label.setObjectName("mutedText"); layout.addWidget(self.last_daily_label)
        self.backup_now_button = QPushButton("Backup Now")
        self.backup_now_button.setObjectName("backupNowButton")
        self.backup_now_button.clicked.connect(self._backup_now); layout.addWidget(self.backup_now_button)
        layout.addWidget(QLabel("Available Backups"))
        self.backup_table = QTableWidget(0, 3)
        self.backup_table.setObjectName("backupTable")
        self.backup_table.setHorizontalHeaderLabels(["Created", "Type", "Size"])
        self.backup_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.backup_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.backup_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.backup_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.backup_table.itemSelectionChanged.connect(self._update_restore_enabled)
        layout.addWidget(self.backup_table)
        self.restore_button = QPushButton("Restore Selected Backup")
        self.restore_button.setObjectName("restoreBackupButton")
        self.restore_button.clicked.connect(self._restore_selected); layout.addWidget(self.restore_button)
        layout.addWidget(QLabel("Performance Diagnostics"))
        self.performance_enabled = QCheckBox("Enable Performance Diagnostics")
        self.performance_enabled.setObjectName("performanceDiagnosticsEnabled")
        self.performance_enabled.setChecked(self.settings.performance_diagnostics_enabled)
        self.performance_enabled.toggled.connect(self._set_performance_enabled)
        layout.addWidget(self.performance_enabled)
        detail = QLabel("Records anonymous local timings only. No task text is collected or transmitted.")
        detail.setObjectName("mutedText")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        self.export_performance_button = QPushButton("Export Performance Diagnostics…")
        self.export_performance_button.clicked.connect(self._export_performance)
        layout.addWidget(self.export_performance_button)
        self.clear_performance_button = QPushButton("Clear Performance Diagnostics")
        self.clear_performance_button.clicked.connect(self._clear_performance)
        layout.addWidget(self.clear_performance_button)
        layout.addStretch()
        writable = data_safety is not None and not data_safety.read_only
        self.backup_now_button.setEnabled(writable)
        self.restore_button.setEnabled(False)
        self.refresh_backups()

    def _set_performance_enabled(self, enabled: bool) -> None:
        self.settings.performance_diagnostics_enabled = enabled

    def _export_performance(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self, "Export Performance Diagnostics", "flowtrack-performance-diagnostics.zip",
            "ZIP archives (*.zip)",
        )
        if not selected:
            return
        try:
            destination = self.performance.export(Path(selected))
        except (OSError, ValueError):
            QMessageBox.warning(self, "Export Failed", "FlowTrack could not export the performance diagnostics.")
            return
        QMessageBox.information(self, "Export Complete", f"Performance diagnostics were exported to:\n\n{destination}")

    def _clear_performance(self) -> None:
        if not self._confirmation(
            "Clear Performance Diagnostics?",
            "Delete all locally retained performance diagnostics? Normal logs and FlowTrack data will not be changed.",
            "Clear Diagnostics",
        ):
            return
        try:
            self.performance.clear()
        except OSError:
            QMessageBox.warning(self, "Clear Failed", "FlowTrack could not clear the performance diagnostics.")
            return
        QMessageBox.information(self, "Diagnostics Cleared", "Performance diagnostics were cleared.")

    def _change_data_location(self) -> None:
        choice = ChangeDataLocationDialog(
            move_enabled=self.data_safety is not None and not self.data_safety.read_only,
            parent=self,
        )
        if choice.exec() != QDialog.DialogCode.Accepted:
            return
        selected = QFileDialog.getExistingDirectory(
            self, "Choose FlowTrack Data Folder", str(self.data_directory.parent)
        )
        if not selected:
            return
        destination = Path(selected)
        try:
            if self.relocation.is_current(destination):
                QMessageBox.information(self, "Data Location Unchanged",
                                        "That folder is already the current data location.")
                return
            if choice.move_selected:
                destination = self.relocation.validate_move_destination(destination)
                if not self._confirm_move(destination):
                    return
                prepared = self.relocation.prepare_move(destination)
                self._commit(prepared, None)
            else:
                destination = self.relocation.validate_existing(destination)
                if not self._confirm_existing(destination):
                    return
                self._commit(None, destination)
        except DataLocationError as error:
            QMessageBox.warning(self, "Data Location Not Changed", str(error))

    def _commit(self, move: PreparedMove | None, existing: Path | None) -> None:
        if self._commit_change is not None:
            self._commit_change(move, existing)
        elif move is not None:
            self.relocation.complete_move(move)
        elif existing is not None:
            self.relocation.adopt_existing(existing)
        if move is not None:
            new_path = move.destination
            message = (f"FlowTrack has safely copied your data to:\n\n{new_path}\n\n"
                       f"Your previous data remains at:\n\n{self.data_directory}\n\n"
                       "FlowTrack will now close. Reopen it to continue using the new location.")
        else:
            new_path = existing
            message = (f"FlowTrack will use:\n\n{new_path}\n\nYour current data remains unchanged at:\n\n"
                       f"{self.data_directory}\n\nFlowTrack will now close. Reopen it to continue.")
        QMessageBox.information(self, "Data Location Changed", message)
        self.restart_requested.emit()

    def _confirm_move(self, destination: Path) -> bool:
        message = (f"FlowTrack will safely copy your current data from:\n\n{self.data_directory}\n\n"
                   f"to:\n\n{destination}\n\nYour original data will remain in its current "
                   "location as a safety copy.\n\nFlowTrack will close after the copy and use the "
                   "new location when you reopen it.")
        return self._confirmation("Move FlowTrack Data?", message, "Move Data")

    def _confirm_existing(self, destination: Path) -> bool:
        message = (f"FlowTrack will switch to:\n\n{destination}\n\nYour current FlowTrack data "
                   f"will remain unchanged at:\n\n{self.data_directory}\n\nFlowTrack will close and use "
                   "the selected dataset when reopened.")
        return self._confirmation("Use Existing FlowTrack Data?", message, "Use This Data")

    def _confirmation(self, title: str, message: str, accept_text: str) -> bool:
        dialog = QMessageBox(parent=self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle(title)
        dialog.setAccessibleName(title)
        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        dialog.button(QMessageBox.StandardButton.Ok).setText(accept_text)
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        dialog.setEscapeButton(QMessageBox.StandardButton.Cancel)
        return QMessageBox.StandardButton(dialog.exec()) == QMessageBox.StandardButton.Ok

    def refresh_backups(self) -> None:
        self._backups = self.data_safety.list_backups() if self.data_safety else []
        self.backup_table.setRowCount(len(self._backups))
        last_daily = next((item for item in self._backups if item.reason.value == "daily"), None)
        if last_daily:
            self.last_daily_label.setText(
                f"Last automatic backup: {last_daily.timestamp:%Y-%m-%d %H:%M} UTC"
            )
        for row, info in enumerate(self._backups):
            valid = info.integrity is None or info.integrity.ok
            values = (f"{info.timestamp:%Y-%m-%d %H:%M} UTC",
                      info.reason.value if valid else f"{info.reason.value} (invalid)",
                      self._format_size(info.size))
            for column, value in enumerate(values):
                self.backup_table.setItem(row, column, QTableWidgetItem(value))
        self._update_restore_enabled()

    def _backup_now(self) -> None:
        if self.data_safety is None:
            return
        try:
            info = self.data_safety.create_manual_backup()
        except (BackupError, OSError):
            QMessageBox.warning(self, "Backup Failed",
                                "FlowTrack could not create and validate the backup.")
            return
        self.refresh_backups()
        QMessageBox.information(self, "Backup Complete", f"Created {info.path.name}.")

    def _update_restore_enabled(self) -> None:
        row = self.backup_table.currentRow()
        valid = row >= 0 and row < len(self._backups) and (
            self._backups[row].integrity is None or self._backups[row].integrity.ok
        )
        writable = self.data_safety is not None and not self.data_safety.read_only
        self.restore_button.setEnabled(writable and valid)

    def _restore_selected(self) -> None:
        row = self.backup_table.currentRow()
        if self.data_safety is None or row < 0:
            return
        message = ("Restore this backup?\n\nYour current FlowTrack database will first be "
                   "preserved as a safety backup. FlowTrack will then replace the current "
                   "database with the selected backup.")
        confirmation = QMessageBox(QMessageBox.Icon.Question, "Restore Backup", message,
                                   parent=self)
        confirmation.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        confirmation.setDefaultButton(QMessageBox.StandardButton.Cancel)
        confirmation.setEscapeButton(QMessageBox.StandardButton.Cancel)
        confirmation.button(QMessageBox.StandardButton.Ok).setText("Restore")
        answer = QMessageBox.StandardButton(confirmation.exec())
        if answer != QMessageBox.StandardButton.Ok:
            return
        try:
            self.data_safety.restore_backup(self._backups[row].path)
        except (BackupError, OSError):
            QMessageBox.warning(self, "Restore Failed",
                                "FlowTrack did not adopt the selected backup. Your safety backup was preserved.")
            return
        QMessageBox.information(self, "Restore Complete",
                                "The backup was restored. FlowTrack will now close; reopen it to continue.")
        self.restart_requested.emit()

    @staticmethod
    def _format_size(size: int) -> str:
        return f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} B"
