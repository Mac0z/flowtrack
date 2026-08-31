"""Reusable semantic presentation mapping for task statuses."""

from flowtrack.domain.enums import TaskStatus
from flowtrack.ui.theme.tokens import Theme


STATUS_COLOR_TOKEN: dict[TaskStatus, str] = {
    TaskStatus.NOT_STARTED: "status_not_started",
    TaskStatus.IN_PROGRESS: "status_in_progress",
    TaskStatus.BLOCKED: "status_blocked",
    TaskStatus.WAITING: "status_waiting",
    TaskStatus.COMPLETE: "status_complete",
    TaskStatus.CANCELLED: "status_cancelled",
}


def status_color(theme: Theme, status: TaskStatus) -> str:
    """Resolve a task status through the active theme's semantic tokens."""
    return str(getattr(theme.colors, STATUS_COLOR_TOKEN[status]))
