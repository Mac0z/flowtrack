"""Calendar-date task rules."""

from datetime import date

from flowtrack.domain.enums import TaskStatus


def is_overdue(*, due_date: date | None, status: TaskStatus, today: date) -> bool:
    """Return whether unfinished, non-cancelled work was due before ``today``."""
    if due_date is None or status in (TaskStatus.COMPLETE, TaskStatus.CANCELLED):
        return False
    return due_date < today
