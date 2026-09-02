"""Focused, non-pixel tests for interactive Gantt planning geometry."""
from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine

from flowtrack.application.projects import ProjectQueryService, ProjectService
from flowtrack.application.task_execution import TaskExecutionService, TaskValidationError
from flowtrack.application.task_queries import TaskRow
from flowtrack.domain.enums import TaskPriority, TaskStatus
from flowtrack.persistence.database import session_factory
from flowtrack.persistence.models import Base
from flowtrack.ui.widgets.gantt_timeline import (
    GanttZoom,
    TimelineRange,
    date_to_x,
    dependency_connectors,
    drag_days,
    move_task_dates,
    pixels_per_day,
    resize_task_due,
    resize_task_start,
    x_to_date,
)


def row(title: str, *, start=None, due=None, predecessors=()) -> TaskRow:
    return TaskRow(uuid4(), title, "", TaskStatus.NOT_STARTED, TaskPriority.MEDIUM,
        uuid4(), "Project", None, None, due, start, 0, 0, (), False, None, 0,
        predecessor_ids=tuple(predecessors))


def test_date_x_round_trip_and_scroll_offset():
    timeline = TimelineRange(date(2026, 8, 1), date(2026, 10, 1))
    value = date(2026, 9, 3)
    for zoom in GanttZoom:
        content_x = date_to_x(value, timeline, zoom)
        assert x_to_date(content_x, timeline, zoom) == value
        assert x_to_date(content_x - 137, timeline, zoom, scroll_offset=137) == value


def test_drag_snaps_to_whole_days_and_range_move_preserves_duration():
    width = pixels_per_day(GanttZoom.WEEK)
    assert drag_days(width * 1.49, GanttZoom.WEEK) == 1
    assert drag_days(width * 1.51, GanttZoom.WEEK) == 2
    changed = move_task_dates(date(2026, 9, 3), date(2026, 9, 7), 2)
    assert changed is not None
    assert (changed.start_date, changed.due_date) == (date(2026, 9, 5), date(2026, 9, 9))
    assert (changed.due_date - changed.start_date).days == 4


def test_single_date_moves_only_stored_dates_and_undated_is_not_movable():
    assert move_task_dates(None, date(2026, 9, 3), 2).due_date == date(2026, 9, 5)  # type: ignore[union-attr]
    assert move_task_dates(None, date(2026, 9, 3), 2).start_date is None  # type: ignore[union-attr]
    assert move_task_dates(date(2026, 9, 3), None, -1).start_date == date(2026, 9, 2)  # type: ignore[union-attr]
    equal = move_task_dates(date(2026, 9, 3), date(2026, 9, 3), 4)
    assert equal and equal.start_date == equal.due_date == date(2026, 9, 7)
    assert move_task_dates(None, None, 10) is None


def test_resize_changes_one_edge_and_rejects_inversion():
    start, due = date(2026, 9, 3), date(2026, 9, 7)
    left = resize_task_start(start, due, 2)
    right = resize_task_due(start, due, -2)
    assert left and (left.start_date, left.due_date) == (date(2026, 9, 5), due)
    assert right and (right.start_date, right.due_date) == (start, date(2026, 9, 5))
    assert resize_task_start(start, due, 5) is None
    assert resize_task_due(start, due, -5) is None


def test_dependency_geometry_uses_visible_predecessor_finish_and_successor_start():
    predecessor = row("First", start=date(2026, 9, 1), due=date(2026, 9, 4))
    successor = row("Second", start=date(2026, 9, 7), due=date(2026, 9, 9), predecessors=(predecessor.id,))
    timeline = TimelineRange(date(2026, 9, 1), date(2026, 9, 30))
    connectors = dependency_connectors([predecessor, successor], timeline, GanttZoom.WEEK,
        row_height=38, horizontal_scroll=20)
    connector = connectors[0]
    assert (connector.predecessor_id, connector.successor_id) == (predecessor.id, successor.id)
    assert connector.points[0][0] == date_to_x(predecessor.due_date, timeline, GanttZoom.WEEK) + pixels_per_day(GanttZoom.WEEK) - 20
    assert connector.points[-1][0] == date_to_x(successor.start_date, timeline, GanttZoom.WEEK) - 20
    assert dependency_connectors([successor], timeline, GanttZoom.WEEK, row_height=38) == []
    assert dependency_connectors([predecessor], timeline, GanttZoom.WEEK, row_height=38) == []


def test_zoom_and_scroll_only_transform_connector_paint_coordinates():
    first = row("First", due=date(2026, 9, 4))
    second = row("Second", start=date(2026, 9, 7), predecessors=(first.id,))
    timeline = TimelineRange(date(2026, 9, 1), date(2026, 9, 30))
    day = dependency_connectors([first, second], timeline, GanttZoom.DAY, row_height=38)[0]
    month = dependency_connectors([first, second], timeline, GanttZoom.MONTH, row_height=38)[0]
    scrolled = dependency_connectors([first, second], timeline, GanttZoom.DAY, row_height=38, horizontal_scroll=50)[0]
    assert day.points[-1][0] > month.points[-1][0]
    assert scrolled.points[-1][0] == day.points[-1][0] - 50
    assert (first.due_date, second.start_date) == (date(2026, 9, 4), date(2026, 9, 7))


def test_project_read_model_exposes_finish_to_start_uuid_relationships():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    projects, tasks = ProjectService(factory), TaskExecutionService(factory)
    project_id = projects.create_project("Plan")
    predecessor_id = tasks.create_task("First", project_id=project_id)
    successor_id = tasks.create_task("Second", project_id=project_id)
    tasks.add_dependency(predecessor_id, successor_id)

    rows = {task.id: task for task in ProjectQueryService(factory).project_tasks(project_id)}

    assert rows[predecessor_id].predecessor_ids == ()
    assert rows[successor_id].predecessor_ids == (predecessor_id,)


def test_application_service_rejects_invalid_date_ranges():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tasks = TaskExecutionService(session_factory(engine))
    with pytest.raises(TaskValidationError, match="Start date"):
        tasks.create_task("Invalid", start_date=date(2026, 9, 8), due_date=date(2026, 9, 7))
    task_id = tasks.create_task("Valid", start_date=date(2026, 9, 3), due_date=date(2026, 9, 7))
    with pytest.raises(TaskValidationError, match="Start date"):
        tasks.update_task(task_id, start_date=date(2026, 9, 8))


def test_confirmed_gantt_change_uses_service_and_cancel_does_not_write(application, monkeypatch):
    from flowtrack.ui.widgets.gantt_view import GanttView

    task = row("Move me", start=date(2026, 9, 3), due=date(2026, 9, 7))
    calls = []
    service = type("Service", (), {"update_task": lambda _self, *args, **kwargs: calls.append((args, kwargs))})()
    queries = type("Queries", (), {"project_tasks": lambda _self, _project_id: [task]})()
    view = GanttView(queries, service)  # type: ignore[arg-type]
    view.project_id = task.project_id
    change = move_task_dates(task.start_date, task.due_date, 2)
    assert change is not None
    monkeypatch.setattr(view, "confirm_date_change", lambda *_args: True)
    assert view.request_date_change(task, change, "move")
    assert calls == [((task.id,), {"start_date": date(2026, 9, 5), "due_date": date(2026, 9, 9)})]
    monkeypatch.setattr(view, "confirm_date_change", lambda *_args: False)
    assert not view.request_date_change(task, change, "move")
    assert len(calls) == 1


def test_failed_gantt_write_reloads_original_rows(application, monkeypatch):
    from flowtrack.ui.widgets.gantt_view import GanttView

    task = row("Move me", start=date(2026, 9, 3), due=date(2026, 9, 7))
    refreshes = []
    queries = type("Queries", (), {"project_tasks": lambda _self, _project_id: (refreshes.append(True), [task])[1]})()
    service = type("Service", (), {"update_task": lambda *_args, **_kwargs: (_ for _ in ()).throw(TaskValidationError("invalid range"))})()
    view = GanttView(queries, service)  # type: ignore[arg-type]
    view.project_id = task.project_id
    monkeypatch.setattr(view, "confirm_date_change", lambda *_args: True)
    monkeypatch.setattr("flowtrack.ui.widgets.gantt_view.QMessageBox.warning", lambda *_args: None)
    change = move_task_dates(task.start_date, task.due_date, 2)
    assert change is not None
    assert not view.request_date_change(task, change, "move")
    assert refreshes and view.tasks == [task]
