"""Automatic and manual progress rules."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from flowtrack.domain.enums import ProgressMode, TaskStatus


class TaskProgressSource(Protocol):
    """The small, persistence-independent task surface used by this service."""

    status: TaskStatus
    progress_mode: ProgressMode
    manual_progress: int
    children: Sequence[TaskProgressSource]


class ProjectProgressSource(Protocol):
    """The project fields needed to calculate progress."""

    progress_mode: ProgressMode
    manual_progress: int
    tasks: Sequence[TaskProgressSource]


def _manual_percentage(value: int) -> float:
    if not 0 <= value <= 100:
        raise ValueError("manual progress must be between 0 and 100")
    return float(value)


def calculate_task_progress(task: TaskProgressSource) -> float:
    """Return task progress, recursively evaluating immediate eligible children.

    A completed status always means 100%. For every other status manual mode
    wins; automatic parents average immediate non-cancelled children and an
    automatic task with no eligible children has the leaf default of 0%.
    """
    return _calculate_task_progress(task, active=set())


def calculate_task_automatic_progress(task: TaskProgressSource) -> float:
    """Return the value the task would have in Automatic mode.

    Child modes remain meaningful; only the supplied task's own manual override
    is ignored.  This supports a mode editor without moving calculation logic
    into the UI.
    """
    if task.status is TaskStatus.COMPLETE:
        return 100.0
    eligible = [child for child in task.children if child.status is not TaskStatus.CANCELLED]
    if not eligible:
        return 0.0
    return sum(_calculate_task_progress(child, active={id(task)}) for child in eligible) / len(eligible)


def _calculate_task_progress(task: TaskProgressSource, active: set[int]) -> float:
    identity = id(task)
    if identity in active:
        raise ValueError("task hierarchy contains a cycle")

    if task.status is TaskStatus.COMPLETE:
        return 100.0
    if task.progress_mode is ProgressMode.MANUAL:
        return _manual_percentage(task.manual_progress)

    eligible_children = [child for child in task.children if child.status is not TaskStatus.CANCELLED]
    if not eligible_children:
        return 0.0

    active.add(identity)
    try:
        return sum(_calculate_task_progress(child, active) for child in eligible_children) / len(eligible_children)
    finally:
        active.remove(identity)


def calculate_project_progress(project: ProjectProgressSource) -> float:
    """Return manual project progress or the mean of eligible top-level tasks."""
    if project.progress_mode is ProgressMode.MANUAL:
        return _manual_percentage(project.manual_progress)

    top_level_tasks = [
        task
        for task in project.tasks
        if getattr(task, "parent_task_id", None) is None and task.status is not TaskStatus.CANCELLED
    ]
    if not top_level_tasks:
        return 0.0
    return sum(calculate_task_progress(task) for task in top_level_tasks) / len(top_level_tasks)
