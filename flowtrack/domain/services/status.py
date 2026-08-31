"""Task status and completion timestamp semantics."""

from datetime import datetime

from flowtrack.domain.enums import TaskStatus


def is_complete(status: TaskStatus) -> bool:
    """Return whether a status represents finished work."""
    return status is TaskStatus.COMPLETE


def is_cancelled(status: TaskStatus) -> bool:
    """Return whether work was intentionally abandoned."""
    return status is TaskStatus.CANCELLED


def completed_at_for_status(
    previous_status: TaskStatus,
    new_status: TaskStatus,
    current_completed_at: datetime | None,
    *,
    now: datetime,
) -> datetime | None:
    """Resolve ``completed_at`` for a status change without reading a clock.

    Entering Complete records the supplied timestamp, an already-complete task
    retains its original timestamp, and leaving Complete clears it.
    """
    if new_status is not TaskStatus.COMPLETE:
        return None
    if previous_status is TaskStatus.COMPLETE and current_completed_at is not None:
        return current_completed_at
    return now
