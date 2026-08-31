"""Task status and completion timestamp semantics."""

from datetime import datetime

from flowtrack.domain.enums import TaskStatus


class IncompleteChildrenError(ValueError):
    """Raised when completion would violate task hierarchy semantics."""


def ensure_children_allow_completion(
    new_status: TaskStatus,
    child_statuses: list[TaskStatus],
) -> None:
    """Reject completion while an immediate, non-cancelled child is unfinished."""
    if new_status is not TaskStatus.COMPLETE:
        return
    if any(status not in (TaskStatus.COMPLETE, TaskStatus.CANCELLED) for status in child_statuses):
        raise IncompleteChildrenError(
            "Task cannot be completed while it has unfinished child tasks. "
            "Complete or cancel the remaining child tasks first."
        )


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
