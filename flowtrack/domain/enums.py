"""Stable values stored by the FlowTrack persistence schema."""

from enum import StrEnum


class ProjectStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETE = "complete"
    ARCHIVED = "archived"


class TaskStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    WAITING = "waiting"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProgressMode(StrEnum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"


class DependencyType(StrEnum):
    FINISH_TO_START = "finish_to_start"
