"""Focused M9A interaction, accessibility, and scale regressions."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine

pytest.importorskip("sqlalchemy")

from flowtrack.application.task_queries import TaskQueryService, TaskRow
from flowtrack.application.task_execution import TaskExecutionService
from flowtrack.domain.enums import TaskPriority, TaskStatus
from flowtrack.persistence.database import session_factory
from flowtrack.persistence.models import Base

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    QT_WIDGETS_AVAILABLE = False
else:
    QT_WIDGETS_AVAILABLE = True


@pytest.fixture
def task_services():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    return TaskExecutionService(factory), TaskQueryService(factory)


def _row(identifier, parent=None, depth=0) -> TaskRow:
    return TaskRow(
        identifier, f"Task {depth}", "", TaskStatus.NOT_STARTED, TaskPriority.MEDIUM,
        None, None, None, None, None, None, 0, depth, (), False, parent, depth,
    )


def test_hierarchy_order_handles_deep_practical_hierarchy_without_recursion() -> None:
    """Large valid hierarchies must not be constrained by Python's recursion limit."""
    rows: list[TaskRow] = []
    parent = None
    for depth in range(1_500):
        identifier = uuid4()
        rows.append(_row(identifier, parent, depth))
        parent = identifier
    parents = {row.id: row.parent_task_id for row in rows}

    ordered = TaskQueryService._hierarchy_order(rows, parents, lambda row: row.sort_order)

    assert [row.id for row in ordered] == [row.id for row in rows]


def test_hierarchy_order_keeps_sorted_sibling_subtrees_together() -> None:
    root_id, first_id, second_id = uuid4(), uuid4(), uuid4()
    root = _row(root_id)
    second = replace(_row(second_id, root_id, 1), sort_order=2)
    first = replace(_row(first_id, root_id, 1), sort_order=1)

    ordered = TaskQueryService._hierarchy_order(
        [second, root, first], {root_id: None, first_id: root_id, second_id: root_id},
        lambda row: row.sort_order,
    )

    assert [row.id for row in ordered] == [root_id, first_id, second_id]


@pytest.mark.skipif(not QT_WIDGETS_AVAILABLE, reason="Qt runtime libraries are unavailable")
def test_read_only_inspector_disables_mutating_controls(application, task_services) -> None:
    from flowtrack.ui.widgets.task_inspector import TaskInspector

    service, queries = task_services
    inspector = TaskInspector(service, queries, read_only=True)

    assert not inspector.title.isEnabled()
    assert not inspector.save_button.isEnabled()
    assert not inspector.add_child_button.isEnabled()
    assert not inspector.delete_button.isEnabled()


@pytest.mark.skipif(not QT_WIDGETS_AVAILABLE, reason="Qt runtime libraries are unavailable")
def test_command_palette_selects_first_visible_filtered_command(application) -> None:
    from flowtrack.ui.dialogs.command_palette import CommandPalette

    palette = CommandPalette()
    palette.command_field.setText("settings")

    assert palette.commands.currentItem().text() == "Open Settings"


@pytest.mark.skipif(not QT_WIDGETS_AVAILABLE, reason="Qt runtime libraries are unavailable")
def test_calendar_routine_confirmation_defaults_to_action_and_escape_cancels(
        application, task_services, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox
    from flowtrack.ui.views.calendar import CalendarView

    service, queries = task_services
    old_due = date(2026, 9, 3)
    new_due = old_due + timedelta(days=1)
    task_id = service.create_task("Reschedule", due_date=old_due)
    view = CalendarView(service, queries)

    def accept(dialog):
        assert dialog.standardButton(dialog.defaultButton()) == QMessageBox.StandardButton.Ok
        assert dialog.standardButton(dialog.escapeButton()) == QMessageBox.StandardButton.Cancel
        assert dialog.button(QMessageBox.StandardButton.Ok).text() == "Move Due Date"
        return QMessageBox.StandardButton.Ok.value

    monkeypatch.setattr(QMessageBox, "exec", accept)
    assert view.request_date_change(task_id, new_due)
    assert queries.task_detail(task_id)["due_date"] == new_due

    monkeypatch.setattr(QMessageBox, "exec", lambda _dialog: QMessageBox.StandardButton.Cancel.value)
    assert not view.request_date_change(task_id, old_due)
    assert queries.task_detail(task_id)["due_date"] == new_due


@pytest.mark.skipif(not QT_WIDGETS_AVAILABLE, reason="Qt runtime libraries are unavailable")
def test_gantt_routine_confirmation_defaults_to_action_and_escape_cancels(
        application, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox
    from flowtrack.ui.widgets.gantt_timeline import DateChange
    from flowtrack.ui.widgets.gantt_view import GanttView

    task = replace(_row(uuid4()), start_date=date(2026, 9, 3), due_date=date(2026, 9, 5))
    calls: list[tuple[object, dict[str, object]]] = []
    service = type("Service", (), {
        "update_task": lambda _self, task_id, **values: calls.append((task_id, values)),
    })()
    queries = type("Queries", (), {"project_tasks": lambda _self, _project_id: [task]})()
    view = GanttView(queries, service)  # type: ignore[arg-type]
    change = DateChange(date(2026, 9, 4), date(2026, 9, 6))

    def accept(dialog):
        assert dialog.standardButton(dialog.defaultButton()) == QMessageBox.StandardButton.Ok
        assert dialog.standardButton(dialog.escapeButton()) == QMessageBox.StandardButton.Cancel
        assert dialog.button(QMessageBox.StandardButton.Ok).text() == "Change Dates"
        return QMessageBox.StandardButton.Ok.value

    monkeypatch.setattr(QMessageBox, "exec", accept)
    assert view.request_date_change(task, change, "move")
    assert calls == [(task.id, {"start_date": change.start_date, "due_date": change.due_date})]

    monkeypatch.setattr(QMessageBox, "exec", lambda _dialog: QMessageBox.StandardButton.Cancel.value)
    assert not view.request_date_change(task, change, "move")
    assert len(calls) == 1


@pytest.mark.skipif(not QT_WIDGETS_AVAILABLE, reason="Qt runtime libraries are unavailable")
def test_destructive_dependency_confirmation_defaults_to_cancel(
        application, task_services, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox
    from flowtrack.ui.widgets.task_inspector import TaskInspector

    service, queries = task_services
    inspector = TaskInspector(service, queries)

    def cancel(dialog):
        assert dialog.standardButton(dialog.defaultButton()) == QMessageBox.StandardButton.Cancel
        assert dialog.standardButton(dialog.escapeButton()) == QMessageBox.StandardButton.Cancel
        return QMessageBox.StandardButton.Cancel.value

    monkeypatch.setattr(QMessageBox, "exec", cancel)
    assert not inspector.confirm_dependency_removal("Approval")
