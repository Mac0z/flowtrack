"""Cross-platform, machine-local advisory locks for dataset writers."""

import hashlib
import os
from pathlib import Path
from typing import BinaryIO

from flowtrack.infrastructure.paths import application_data_directory


def local_lock_path(dataset: Path, *, state_directory: Path | None = None) -> Path:
    """Map a dataset identity to a lock in machine-local application storage."""
    identity = os.path.normcase(str(Path(dataset).resolve())).encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()
    root = state_directory or application_data_directory()
    return root / "locks" / f"{digest}.lock"


class DatasetLock:
    """A non-blocking OS advisory lock held for the lifetime of this object."""

    def __init__(self, dataset: Path, *, state_directory: Path | None = None) -> None:
        self.path = local_lock_path(dataset, state_directory=state_directory)
        self._file: BinaryIO | None = None

    def acquire(self) -> bool:
        if self._file is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                if handle.read(1) == b"":
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError):
            handle.close()
            return False
        self._file = handle
        return True

    def release(self) -> None:
        handle, self._file = self._file, None
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self) -> "DatasetLock":
        if not self.acquire():
            raise RuntimeError("dataset write lock is already held")
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()
