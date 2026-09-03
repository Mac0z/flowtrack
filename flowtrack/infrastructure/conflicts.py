"""Non-destructive detection of plausible synchronisation conflict databases."""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from flowtrack.infrastructure.backup import check_integrity
from flowtrack.infrastructure.dataset import DatasetPaths

logger = logging.getLogger(__name__)
_COPY_WORDS = re.compile(r"(?:conflict(?:ed)?|copy|duplicate|\(\d+\))", re.IGNORECASE)
_DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".database"}
_SIDECARS = {"flowtrack.db-wal", "flowtrack.db-shm", "flowtrack.db-journal"}


@dataclass(frozen=True)
class ConflictCandidate:
    path: Path
    filename: str
    size: int
    modified_utc: datetime
    sqlite_valid: bool
    reason: str


@dataclass(frozen=True)
class ConflictScanResult:
    canonical: Path
    candidates: tuple[ConflictCandidate, ...]

    @property
    def has_conflicts(self) -> bool:
        return bool(self.candidates)


def scan_dataset_conflicts(paths: DatasetPaths) -> ConflictScanResult:
    """Inspect only the dataset root, without writing to any candidate."""
    candidates: list[ConflictCandidate] = []
    if paths.root.is_dir():
        for candidate in paths.root.iterdir():
            name = candidate.name
            lowered = name.casefold()
            if (not candidate.is_file() or lowered == "flowtrack.db"
                    or lowered in _SIDECARS or name.startswith(".")):
                continue
            stem = candidate.stem.casefold()
            if (candidate.suffix.casefold() not in _DATABASE_SUFFIXES
                    or not stem.startswith("flowtrack")):
                continue
            tail = stem[len("flowtrack"):]
            strongly_named = bool(_COPY_WORDS.search(tail))
            # Provider conflict names are inconsistent. A FlowTrack-prefixed DB with a
            # separator is still worth surfacing, while flowtracker.db is not.
            provider_variant = bool(tail) and tail[0] in " (-_"
            if not (strongly_named or provider_variant):
                continue
            stat = candidate.stat()
            candidates.append(ConflictCandidate(
                candidate, name, stat.st_size,
                datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                check_integrity(candidate).ok,
                "conflict/copy naming" if strongly_named else "alternate FlowTrack database name",
            ))
    result = ConflictScanResult(
        paths.database, tuple(sorted(candidates, key=lambda item: item.filename.casefold()))
    )
    logger.info("Dataset conflict scan performed: %d candidate(s): %s",
                len(result.candidates), ", ".join(c.filename for c in result.candidates) or "none")
    return result
