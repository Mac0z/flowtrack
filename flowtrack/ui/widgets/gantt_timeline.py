"""Deterministic geometry, interaction, and hierarchy helpers for the Gantt."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from collections.abc import Iterable, Sequence
from uuid import UUID

from flowtrack.application.task_queries import TaskRow
from flowtrack.domain.enums import TaskStatus


class GanttZoom(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class GanttInteraction(StrEnum):
    """Mutually exclusive pointer interactions supported by the timeline."""

    NONE = ""
    DEPENDENCY = "dependency"
    RESIZE_START = "resize_start"
    RESIZE_DUE = "resize_due"
    MOVE = "move"


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


@dataclass(frozen=True, slots=True)
class DateChange:
    """A proposed, not-yet-persisted task date change."""
    start_date: date | None
    due_date: date | None


@dataclass(frozen=True, slots=True)
class ConnectorGeometry:
    predecessor_id: UUID
    successor_id: UUID
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class DependencyHandleGeometry:
    """Dependency handle in viewport coordinates, including its hit target."""

    centre_x: float
    centre_y: float
    hit_left: float
    hit_top: float
    hit_size: float


@dataclass(frozen=True, slots=True)
class MonthSegment:
    """The inclusive portion of one calendar month visible on a timeline."""

    start: date
    end: date
    label: str


WEEKDAY_ABBREVIATIONS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def day_header_month_segments(timeline: TimelineRange) -> list[MonthSegment]:
    """Split a timeline into calendar-month spans without changing its dates."""
    segments: list[MonthSegment] = []
    cursor = timeline.start
    while cursor <= timeline.end:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        segment_end = min(timeline.end, next_month - timedelta(days=1))
        segments.append(MonthSegment(cursor, segment_end, cursor.strftime("%B %Y").upper()))
        cursor = segment_end + timedelta(days=1)
    return segments


def day_header_labels(value: date) -> tuple[str, str]:
    """Return stable, locale-independent labels for a real calendar date."""
    return WEEKDAY_ABBREVIATIONS[value.weekday()], str(value.day)


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


def x_to_date(x: float, timeline: TimelineRange, zoom: GanttZoom, *, scroll_offset: float = 0) -> date:
    """Convert viewport X to a calendar date, including horizontal scrolling."""
    days = round((x + scroll_offset) / pixels_per_day(zoom))
    return timeline.start + timedelta(days=days)


def drag_days(pixel_delta: float, zoom: GanttZoom) -> int:
    """Snap a horizontal movement to the nearest whole calendar day."""
    return round(pixel_delta / pixels_per_day(zoom))


def move_task_dates(start: date | None, due: date | None, days: int) -> DateChange | None:
    """Move every actually stored date; undated tasks cannot be moved."""
    if start is None and due is None:
        return None
    delta = timedelta(days=days)
    return DateChange(start + delta if start else None, due + delta if due else None)


def resize_task_start(start: date | None, due: date | None, days: int) -> DateChange | None:
    if start is None or due is None:
        return None
    candidate = start + timedelta(days=days)
    return DateChange(candidate, due) if candidate <= due else None


def resize_task_due(start: date | None, due: date | None, days: int) -> DateChange | None:
    if start is None or due is None:
        return None
    candidate = due + timedelta(days=days)
    return DateChange(start, candidate) if candidate >= start else None


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


def dependency_source_eligible(task: TaskRow) -> bool:
    """Direct Gantt creation requires a stable dated anchor and an active source."""
    return (task.start_date is not None or task.due_date is not None) and task.status not in {
        TaskStatus.COMPLETE, TaskStatus.CANCELLED,
    }


def dependency_target_eligible(source: TaskRow, target: TaskRow) -> bool:
    """Apply cheap UI checks; the application service remains cycle authority."""
    return (
        source.id != target.id
        and target.status not in {TaskStatus.COMPLETE, TaskStatus.CANCELLED}
        and source.id not in target.predecessor_ids
    )


def dependency_handle_geometry(
    task: TaskRow, timeline: TimelineRange, zoom: GanttZoom, *, row_index: int,
    row_height: float, header_height: float = 0, horizontal_scroll: float = 0,
    vertical_scroll: float = 0, gap: float = 9, hit_size: float = 18,
    milestone_half_width: float = 7,
) -> DependencyHandleGeometry | None:
    """Place a forgiving handle just beyond a dated bar or milestone's right edge."""
    if not dependency_source_eligible(task):
        return None
    bar = task_bar_geometry(task, timeline, zoom)
    if bar is None:
        return None
    task_end = bar.x + (milestone_half_width if bar.milestone else bar.width)
    centre_x = task_end + gap - horizontal_scroll
    centre_y = header_height + (row_index + .5) * row_height - vertical_scroll
    return DependencyHandleGeometry(
        centre_x, centre_y, centre_x - hit_size / 2, centre_y - hit_size / 2, hit_size,
    )


def visible_row_at_y(
    rows: Sequence[TaskRow], viewport_y: float, *, header_height: float,
    row_height: float, vertical_scroll: float = 0,
) -> TaskRow | None:
    """Return only a row present in the supplied (already hierarchy-filtered) model."""
    if viewport_y < header_height:
        return None
    index = int((viewport_y - header_height + vertical_scroll) // row_height)
    return rows[index] if 0 <= index < len(rows) else None


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


def dependency_connectors(
    tasks: Sequence[TaskRow], timeline: TimelineRange, zoom: GanttZoom, *,
    row_height: float, header_height: float = 0, horizontal_scroll: float = 0,
    vertical_scroll: float = 0,
) -> list[ConnectorGeometry]:
    """Route visible Finish-to-Start edges in viewport coordinates."""
    by_id = {task.id: (index, task) for index, task in enumerate(tasks)}
    connectors: list[ConnectorGeometry] = []
    for successor_index, successor in enumerate(tasks):
        successor_date = successor.start_date or successor.due_date
        if successor_date is None:
            continue
        for predecessor_id in successor.predecessor_ids:
            predecessor_entry = by_id.get(predecessor_id)
            if predecessor_entry is None:
                continue
            predecessor_index, predecessor = predecessor_entry
            predecessor_date = predecessor.due_date or predecessor.start_date
            if predecessor_date is None:
                continue
            start_x = date_to_x(predecessor_date, timeline, zoom) + pixels_per_day(zoom) - horizontal_scroll
            end_x = date_to_x(successor_date, timeline, zoom) - horizontal_scroll
            start_y = header_height + (predecessor_index + .5) * row_height - vertical_scroll
            end_y = header_height + (successor_index + .5) * row_height - vertical_scroll
            elbow_x = max(start_x + 8, min(end_x - 8, (start_x + end_x) / 2))
            connectors.append(ConnectorGeometry(predecessor_id, successor.id,
                ((start_x, start_y), (elbow_x, start_y), (elbow_x, end_y), (end_x, end_y))))
    return connectors
