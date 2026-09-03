"""Application boundary for user-initiated backup and restore operations."""

from pathlib import Path
from typing import Callable

from flowtrack.infrastructure.backup import BackupInfo, BackupManager, BackupReason


class ReadOnlySafetyError(RuntimeError):
    pass


class DataSafetyService:
    def __init__(self, manager: BackupManager, *, read_only: bool,
                 close_connections: Callable[[], None]) -> None:
        self._manager = manager
        self.read_only = read_only
        self._close_connections = close_connections

    def list_backups(self, *, validate: bool = True) -> list[BackupInfo]:
        return self._manager.list_backups(validate=validate)

    def create_manual_backup(self) -> BackupInfo:
        self._require_writable()
        return self._manager.create(BackupReason.MANUAL)

    def restore_backup(self, source: Path) -> BackupInfo:
        self._require_writable()
        return self._manager.restore(source, close_connections=self._close_connections)

    def _require_writable(self) -> None:
        if self.read_only:
            raise ReadOnlySafetyError("Backup changes are unavailable in read-only mode.")
