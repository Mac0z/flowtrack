"""Focused geometry and integration coverage for direct Gantt dependencies."""
from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine

from flowtrack.application.task_execution import TaskExecutionService, TaskValidationError
from flowtrack.application.task_queries import TaskRow
from flowtrack.domain.enums import TaskPriority, TaskStatus
from flowtrack.persistence.database import session_factory
from flowtrack.persistence.models import Base
from flowtrack.ui.widgets.gantt_timeline import (
    GanttZoom,
    TimelineRange,
    date_to_x,
    dependency_handle_geometry,
    dependency_source_eligible,
    dependency_target_eligible,
    pixels_per_day,
    visible_hierarchy,
    visible_row_at_y,
)


def row(title: str, *, start=date(2026, 9, 3), due=date(2026, 9, 7),
        status=TaskStatus.NOT_STARTED, predecessors=(), parent=None, depth=0) -> TaskRow:
    return TaskRow(uuid4(), title, "", status, TaskPriority.MEDIUM,
        uuid4(), "Project", None, None, due, start, 0, 0, (), False, parent, depth,
        predecessor_ids=tuple(predecessors))


def test_dependency_handle_geometry_for_bar_milestone_and_scroll():
    timeline = TimelineRange(date(2026, 9, 1), date(2026, 9, 30))
    bar = row("Bar")
    handle = dependency_handle_geometry(bar, timeline, GanttZoom.WEEK,
        row_index=1, row_height=38, header_height=42, horizontal_scroll=20,
        vertical_scroll=5)
    assert handle is not None
    expected_end = date_to_x(bar.due_date, timeline, GanttZoom.WEEK) + pixels_per_day(GanttZoom.WEEK)
    assert handle.centre_x == expected_end + 9 - 20
    assert handle.centre_y == 42 + 1.5 * 38 - 5

    milestone = replace(bar, start_date=None)
    milestone_handle = dependency_handle_geometry(milestone, timeline, GanttZoom.WEEK,
        row_index=0, row_height=38)
    assert milestone_handle is not None
    assert milestone_handle.centre_x == date_to_x(milestone.due_date, timeline, GanttZoom.WEEK) + 7 + 9


def test_visible_row_lookup_accounts_for_scroll_and_collapsed_rows():
    parent = row("Parent")
    child = row("Child", parent=parent.id, depth=1)
    other = row("Other")
    visible = visible_hierarchy([parent, child, other], {parent.id})
    assert visible == [parent, other]
    assert visible_row_at_y(visible, 42 + 4, header_height=42, row_height=38) is parent
    assert visible_row_at_y(visible, 42 + 4, header_height=42, row_height=38,
                            vertical_scroll=38) is other
    assert visible_row_at_y(visible, 10, header_height=42, row_height=38) is None
    assert child not in visible


def test_dependency_source_and_target_eligibility():
    source = row("Source")
    target = row("Target")
    assert dependency_source_eligible(source)
    assert dependency_target_eligible(source, target)
    assert not dependency_target_eligible(source, source)
    assert not dependency_target_eligible(source, replace(target, status=TaskStatus.COMPLETE))
    assert not dependency_target_eligible(source, replace(target, status=TaskStatus.CANCELLED))
    assert not dependency_target_eligible(source, replace(target, predecessor_ids=(source.id,)))
    assert not dependency_source_eligible(replace(source, status=TaskStatus.COMPLETE))
    assert not dependency_source_eligible(replace(source, status=TaskStatus.CANCELLED))
    assert not dependency_source_eligible(replace(source, start_date=None, due_date=None))


def test_application_service_remains_status_and_cycle_authority():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    service = TaskExecutionService(session_factory(engine))
    source = service.create_task("Source")
    target = service.create_task("Target")
    service.update_task(target, status=TaskStatus.COMPLETE)
    with pytest.raises(TaskValidationError, match="Completed or cancelled"):
        service.add_dependency(source, target)

    service.update_task(target, status=TaskStatus.NOT_STARTED)
    service.add_dependency(source, target)
    with pytest.raises(TaskValidationError, match="circular"):
        service.add_dependency(target, source)


def test_temporary_connector_has_unfilled_path_and_balanced_painter_state():
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor
    from flowtrack.ui.widgets.gantt_view import paint_temporary_dependency_connector

    class Painter:
        saved = 0
        restored = 0
        brush = None
        path_brush = None
        def save(self): self.saved += 1
        def restore(self): self.restored += 1
        def setPen(self, _pen): pass
        def setBrush(self, brush): self.brush = brush
        def drawPath(self, _path): self.path_brush = self.brush

    painter = Painter()
    paint_temporary_dependency_connector(
        painter, QPointF(1, 2), QPointF(4, 5), QColor("#778899"))  # type: ignore[arg-type]
    assert painter.path_brush is Qt.BrushStyle.NoBrush
    assert (painter.saved, painter.restored) == (1, 1)


def test_handle_drag_is_separate_and_emits_predecessor_then_successor(application):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from flowtrack.ui.widgets.gantt_timeline import GanttInteraction
    from flowtrack.ui.widgets.gantt_view import GanttTimeline

    source, target = row("Source"), row("Target", start=date(2026, 9, 10), due=date(2026, 9, 12))
    timeline_range = TimelineRange(date(2026, 9, 1), date(2026, 9, 30))
    widget = GanttTimeline()
    widget.resize(900, 220)
    widget.set_rows([source, target], timeline_range, GanttZoom.WEEK)
    handle = widget._handle_for(source)
    assert handle is not None
    start = QPointF(handle.centre_x, handle.centre_y)
    destination = QPointF(500, widget.header_height + 1.5 * 38)
    requested: list[tuple[object, object]] = []
    date_changes: list[object] = []
    widget.dependency_requested.connect(lambda predecessor, successor:
                                        requested.append((predecessor, successor)))
    widget.date_change_requested.connect(lambda *change: date_changes.append(change))

    widget.mousePressEvent(QMouseEvent(
        QEvent.Type.MouseButtonPress, start, start, Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert widget._interaction is GanttInteraction.DEPENDENCY
    widget.mouseMoveEvent(QMouseEvent(
        QEvent.Type.MouseMove, destination, destination, Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert widget._preview is None
    widget.mouseReleaseEvent(QMouseEvent(
        QEvent.Type.MouseButtonRelease, destination, destination, Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))

    assert requested == [(source.id, target.id)]
    assert date_changes == []
    assert (source.start_date, source.due_date) == (date(2026, 9, 3), date(2026, 9, 7))


def test_view_dependency_request_calls_service_refreshes_and_preserves_state(application, monkeypatch):
    from flowtrack.ui.widgets.gantt_view import GanttView

    source, target = row("Source"), row("Target")
    calls: list[tuple[object, object]] = []
    queries = type("Queries", (), {"project_tasks": lambda _self, _project: [source, target]})()
    service = type("Service", (), {
        "add_dependency": lambda _self, predecessor, successor: calls.append((predecessor, successor)),
    })()
    view = GanttView(queries, service)  # type: ignore[arg-type]
    view.project_id = source.project_id
    view.zoom = GanttZoom.MONTH
    view.collapsed.add(source.id)
    changes: list[bool] = []
    view.data_changed.connect(lambda: changes.append(True))

    assert view.request_dependency(source.id, target.id)
    assert calls == [(source.id, target.id)]
    assert view.zoom is GanttZoom.MONTH
    assert source.id in view.collapsed
    assert changes == [True]

    service.add_dependency = lambda *_args: (_ for _ in ()).throw(TaskValidationError("cycle"))
    warnings: list[str] = []
    monkeypatch.setattr("flowtrack.ui.widgets.gantt_view.QMessageBox.warning",
                        lambda _parent, _title, message: warnings.append(message))
    assert not view.request_dependency(target.id, source.id)
    assert warnings and "cycle" not in warnings[0]
