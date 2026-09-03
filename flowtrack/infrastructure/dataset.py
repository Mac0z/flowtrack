"""Portable FlowTrack dataset layout and backwards-compatible selection."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class DataDirectorySettings(Protocol):
    data_directory: Path | None


@dataclass(frozen=True)
class DatasetPaths:
    """All paths belonging to one user-selected dataset."""

    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root).expanduser())

    @property
    def database(self) -> Path:
        return self.root / "flowtrack.db"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def attachments(self) -> Path:
        return self.root / "attachments"

    @property
    def session_lease(self) -> Path:
        return self.root / ".flowtrack-session.json"

    def initialise(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.backups.mkdir(exist_ok=True)
        self.attachments.mkdir(exist_ok=True)


def resolve_saved_or_legacy_dataset(
    settings: DataDirectorySettings, legacy_database: Path
) -> DatasetPaths | None:
    """Resolve a saved dataset, adopting (but never moving) a legacy database."""
    selected = settings.data_directory
    if selected is not None:
        return DatasetPaths(selected)
    if legacy_database.is_file():
        settings.data_directory = legacy_database.parent
        return DatasetPaths(legacy_database.parent)
    return None
