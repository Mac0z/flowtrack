"""Focused M9A interaction, accessibility, and scale regressions."""
from __future__ import annotations

from dataclasses import replace
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
