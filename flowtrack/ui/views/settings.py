"""Data-location, backup, and restore settings."""

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from flowtrack.application.data_safety import DataSafetyService
from flowtrack.infrastructure.backup import BackupError, BackupInfo


class SettingsView(QWidget):
    restart_requested = Signal()

    def __init__(self, data_directory: Path,
                 data_safety: DataSafetyService | None = None) -> None:
        super().__init__()
        self.data_safety = data_safety
        self._backups: list[BackupInfo] = []
        layout = QVBoxLayout(self)
        title = QLabel("Settings"); title.setObjectName("pageTitle"); layout.addWidget(title)
        layout.addWidget(QLabel("Data"))
        location = QLabel(str(data_directory)); location.setObjectName("mutedText")
        layout.addWidget(location)
        open_folder = QPushButton("Open Data Folder")
        open_folder.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_directory)))
        )
        layout.addWidget(open_folder)
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
        layout.addStretch()
        writable = data_safety is not None and not data_safety.read_only
        self.backup_now_button.setEnabled(writable)
        self.restore_button.setEnabled(False)
        self.refresh_backups()

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
