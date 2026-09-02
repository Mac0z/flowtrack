"""Deterministic geometry and hierarchy helpers for the read-only Gantt."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from collections.abc import Iterable, Sequence
from uuid import UUID

from flowtrack.application.task_queries import TaskRow


class GanttZoom(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


PIXELS_PER_DAY = {GanttZoom.DAY: 42.0, GanttZoom.WEEK: 18.0, GanttZoom.MONTH: 6.0}
PADDING_DAYS = {GanttZoom.DAY: 3, GanttZoom.WEEK: 14, GanttZoom.MONTH: 31}


@dataclass(frozen=True, slots=True)
class TimelineRange:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


@dataclass(frozen=True, slots=True)
class BarGeometry:
    """A bar in content coordinates; milestones use their centre as ``x``."""
    x: float
    width: float
    progress_width: float
    milestone: bool


def pixels_per_day(zoom: GanttZoom) -> float:
    return PIXELS_PER_DAY[zoom]


def calculate_timeline_range(
    tasks: Iterable[TaskRow], *, zoom: GanttZoom = GanttZoom.WEEK,
    project_start: date | None = None, project_due: date | None = None,
    today: date | None = None,
) -> TimelineRange:
    dates = [value for task in tasks for value in (task.start_date, task.due_date) if value]
    dates.extend(value for value in (project_start, project_due) if value)
    if dates:
        padding = timedelta(days=PADDING_DAYS[zoom])
        return TimelineRange(min(dates) - padding, max(dates) + padding)
    centre = today or date.today()
    half_span = {GanttZoom.DAY: 14, GanttZoom.WEEK: 42, GanttZoom.MONTH: 92}[zoom]
    return TimelineRange(centre - timedelta(days=half_span), centre + timedelta(days=half_span))


def date_to_x(value: date, timeline: TimelineRange, zoom: GanttZoom) -> float:
    return (value - timeline.start).days * pixels_per_day(zoom)


def task_bar_geometry(task: TaskRow, timeline: TimelineRange, zoom: GanttZoom) -> BarGeometry | None:
    start, due = task.start_date, task.due_date
    if start is None and due is None:
        return None
    single = start is None or due is None or start == due
    if single:
        value = start or due
        assert value is not None
        return BarGeometry(date_to_x(value, timeline, zoom), 0.0, 0.0, True)
    assert start is not None and due is not None
    # Invalid legacy ranges remain visible rather than producing negative geometry.
    first, last = min(start, due), max(start, due)
    width = ((last - first).days + 1) * pixels_per_day(zoom)
    progress = max(0.0, min(100.0, float(task.progress)))
    return BarGeometry(date_to_x(first, timeline, zoom), width, width * progress / 100.0, False)


def visible_hierarchy(tasks: Sequence[TaskRow], collapsed: set[UUID]) -> list[TaskRow]:
    """Hide every descendant of a collapsed row, including deep descendants."""
    hidden_depth: int | None = None
    visible: list[TaskRow] = []
    for task in tasks:
        if hidden_depth is not None:
            if task.hierarchy_depth > hidden_depth:
                continue
            hidden_depth = None
        visible.append(task)
        if task.id in collapsed:
            hidden_depth = task.hierarchy_depth
    return visible


def parent_ids(tasks: Sequence[TaskRow]) -> set[UUID]:
    identifiers = {task.id for task in tasks}
    return {task.parent_task_id for task in tasks if task.parent_task_id in identifiers}  # type: ignore[misc]


def collapsed_descendant_dates(parent: TaskRow, tasks: Sequence[TaskRow]) -> tuple[date | None, date | None]:
    """Return a display-only descendant span, preferring explicit parent dates."""
    if parent.start_date or parent.due_date:
        return parent.start_date, parent.due_date
    try:
        index = next(i for i, task in enumerate(tasks) if task.id == parent.id)
    except StopIteration:
        return None, None
    descendants: list[date] = []
    for task in tasks[index + 1:]:
        if task.hierarchy_depth <= parent.hierarchy_depth:
            break
        descendants.extend(value for value in (task.start_date, task.due_date) if value)
    return (min(descendants), max(descendants)) if descendants else (None, None)
