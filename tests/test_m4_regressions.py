"""Regression coverage for the targeted M4 usability and persistence fixes."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("PySide6")

from sqlalchemy import create_engine, select

from flowtrack.application import TaskExecutionService, TaskQueryService
from flowtrack.domain.enums import ProgressMode, TaskPriority, TaskStatus
from flowtrack.persistence.database import create_database_engine, session_factory
from flowtrack.persistence.models import Base, Dependency, Task
from flowtrack.ui.dialogs.quick_capture import QuickCaptureDialog
from flowtrack.ui.theme.dark import DARK_THEME
from flowtrack.ui.theme.status import STATUS_COLOR_TOKEN, status_color
from flowtrack.ui.widgets.task_inspector import TaskInspector


@pytest.fixture
def services():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    return TaskExecutionService(factory), TaskQueryService(factory), factory


def test_inspector_loads_and_saves_all_persisted_metadata(application, services):
    commands, queries, _ = services
    owner_id = commands.create_owner("Morgan")
    tag_id = commands.create_tag("Deep work")
    task_id = commands.create_task(
        "Persisted title", description="Persisted description", owner_id=owner_id,
        start_date=date(2026, 9, 10), due_date=date(2026, 9, 21),
        priority=TaskPriority.CRITICAL,
    )
    commands.update_task(
        task_id, status=TaskStatus.IN_PROGRESS,
        progress_mode=ProgressMode.MANUAL, manual_progress=37,
    )
    commands.set_tags(task_id, [tag_id])

    inspector = TaskInspector(commands, queries)
    inspector.load_task(task_id)

    assert inspector.title.text() == "Persisted title"
    assert inspector.description.toPlainText() == "Persisted description"
    assert inspector.status.currentData() == TaskStatus.IN_PROGRESS.value
    assert inspector.priority.currentData() == TaskPriority.CRITICAL.value
    assert inspector.owner.currentData() == str(owner_id)
    assert inspector.start.date_or_none() == date(2026, 9, 10)
    assert inspector.due.date_or_none() == date(2026, 9, 21)
    assert inspector.progress.value() == 37
    assert inspector.progress_mode.currentData() == ProgressMode.MANUAL.value
    assert not inspector.progress.isReadOnly()
    assert inspector.assigned_tag_ids == {str(tag_id)}
    assert inspector.available_tags.findData(str(tag_id)) == -1

    inspector.start.set_date_or_none(date(2026, 10, 1))
    inspector.due.set_date_or_none(None)
    inspector.save()
    detail = queries.task_detail(task_id)
    assert detail is not None
    assert detail["start_date"] == date(2026, 10, 1)
    assert detail["due_date"] is None


def test_inspector_progress_modes_load_switch_and_persist(application, services):
    commands, queries, _ = services
    parent = commands.create_task("Parent")
    child = commands.create_task("Child", parent_task_id=parent)
    commands.complete_task(child)
    inspector = TaskInspector(commands, queries)
    inspector.load_task(parent)

    assert inspector.progress_mode.currentData() == ProgressMode.AUTOMATIC.value
    assert inspector.progress.value() == 100
    assert inspector.progress.isReadOnly()

    inspector._select_data(inspector.progress_mode, ProgressMode.MANUAL.value)
    assert inspector.progress.value() == 100
    assert not inspector.progress.isReadOnly()
    inspector.progress.setValue(73)
    inspector.save()
    detail = queries.task_detail(parent)
    assert detail["progress_mode"] is ProgressMode.MANUAL
    assert detail["manual_progress"] == 73
    assert detail["status"] is TaskStatus.NOT_STARTED

    inspector._select_data(inspector.progress_mode, ProgressMode.AUTOMATIC.value)
    assert inspector.progress.value() == 100
    assert inspector.progress.isReadOnly()
    inspector.save()
    reopened = queries.task_detail(parent)
    assert reopened["progress_mode"] is ProgressMode.AUTOMATIC
    assert reopened["manual_progress"] == 73


def test_inspector_represents_null_dates_as_intentional_none(application, services):
    commands, queries, _ = services
    task_id = commands.create_task("No dates")
    inspector = TaskInspector(commands, queries)
    inspector.load_task(task_id)
    assert inspector.start.date_or_none() is None
    assert inspector.due.date_or_none() is None
    assert inspector.start.text() == "None"
    assert inspector.due.text() == "None"
    assert "1752" not in inspector.start.text()
    assert "1752" not in inspector.due.text()


def test_nullable_date_clear_and_real_historic_date(application, services):
    commands, queries, _ = services
    task_id = commands.create_task("Historic", start_date=date(1801, 2, 3))
    inspector = TaskInspector(commands, queries)
    inspector.load_task(task_id)
    assert inspector.start.date_or_none() == date(1801, 2, 3)
    inspector.start.clear_date()
    inspector.save()
    assert queries.task_detail(task_id)["start_date"] is None


def test_inspector_tag_assignment_workflow_and_exact_persistence(application, services):
    commands, queries, _ = services
    assigned = commands.create_tag("Assigned")
    available = commands.create_tag("Available")
    task_id = commands.create_task("Tagged")
    commands.set_tags(task_id, [assigned])
    inspector = TaskInspector(commands, queries)
    inspector.load_task(task_id)

    assert inspector.assigned_tag_ids == {str(assigned)}
    assert inspector.available_tags.findData(str(assigned)) == -1
    assert inspector.available_tags.findData(str(available)) >= 0
    inspector.available_tags.setCurrentIndex(inspector.available_tags.findData(str(available)))
    inspector.add_selected_tag()
    assert inspector.assigned_tag_ids == {str(assigned), str(available)}
    assert inspector.available_tags.findData(str(available)) == -1
    inspector.remove_tag(str(assigned))
    assert inspector.assigned_tag_ids == {str(available)}
    assert inspector.available_tags.findData(str(assigned)) >= 0
    inspector.save()

    reopened = TaskInspector(commands, queries)
    reopened.load_task(task_id)
    assert reopened.assigned_tag_ids == {str(available)}
    assert queries.task_detail(task_id)["tags"] == ((available, "Available"),)


def test_inspector_no_tags_empty_state(application, services):
    commands, queries, _ = services
    inspector = TaskInspector(commands, queries)
    inspector.load_task(commands.create_task("Untagged"))
    assert not inspector.assigned_tag_ids
    assert not inspector.no_tags.isHidden()


def test_add_child_defaults_dates_and_opens_child(application, services):
    commands, queries, _ = services
    parent = commands.create_task("Parent")
    inspector = TaskInspector(commands, queries)
    inspector.load_task(parent)
    today = date.today()
    inspector.add_child()
    detail = queries.task_detail(inspector.task_id)
    assert detail["start_date"] == today
    assert detail["due_date"] == today + timedelta(days=1)
    assert inspector.start.date_or_none() == today
    assert inspector.due.date_or_none() == today + timedelta(days=1)


def test_inspector_selects_inactive_current_owner(application, services):
    commands, queries, _ = services
    owner_id = commands.create_owner("Former owner")
    task_id = commands.create_task("Assigned", owner_id=owner_id)
    commands.update_owner(owner_id, is_active=False)
    inspector = TaskInspector(commands, queries)
    inspector.load_task(task_id)
    assert inspector.owner.currentData() == str(owner_id)
    assert inspector.owner.currentText() == "Former owner (inactive)"


def test_quick_capture_defaults_dates_each_time_opened(application, services):
    commands, queries, _ = services
    dialog = QuickCaptureDialog(commands, queries)
    expected = date.today()
    dialog.start_edit.set_date_or_none(date(2020, 1, 1))
    dialog.due_edit.set_date_or_none(None)
    dialog.open()
    assert dialog.start_edit.date_or_none() == expected
    assert dialog.due_edit.date_or_none() == expected + timedelta(days=1)
    dialog.close()


def test_quick_capture_persists_custom_dates(application, services):
    commands, queries, _ = services
    dialog = QuickCaptureDialog(commands, queries)
    dialog.title_edit.setText("Captured")
    dialog.start_edit.set_date_or_none(date(2026, 11, 4))
    dialog.due_edit.set_date_or_none(date(2026, 11, 8))
    created: list[object] = []
    dialog.task_created.connect(created.append)
    dialog.submit()
    detail = queries.task_detail(created[0])
    assert detail is not None
    assert detail["start_date"] == date(2026, 11, 4)
    assert detail["due_date"] == date(2026, 11, 8)


def test_delete_leaf_removes_detail(services):
    commands, queries, _ = services
    task_id = commands.create_task("Leaf")
    commands.delete_task(task_id)
    assert queries.task_detail(task_id) is None
    assert task_id not in {row.id for row in queries.my_tasks()}


def test_delete_hierarchy_and_referencing_dependencies(services):
    commands, queries, factory = services
    parent_id = commands.create_task("Parent")
    child_id = commands.create_task("Child", parent_task_id=parent_id)
    other_id = commands.create_task("Other")
    commands.add_dependency(child_id, other_id)
    commands.delete_task(parent_id, allow_with_children=True)
    assert queries.task_detail(parent_id) is None
    assert queries.task_detail(child_id) is None
    with factory() as session:
        assert session.scalar(select(Dependency)) is None


def test_deletion_survives_file_database_reopen(tmp_path):
    path = tmp_path / "flowtrack.sqlite3"
    engine = create_database_engine(path)
    Base.metadata.create_all(engine)
    commands = TaskExecutionService(session_factory(engine))
    task_id = commands.create_task("Persist then delete")
    commands.delete_task(task_id)
    engine.dispose()

    reopened = create_database_engine(path)
    factory = session_factory(reopened)
    assert TaskQueryService(factory).task_detail(task_id) is None
    with factory() as session:
        assert session.scalar(select(Task).where(Task.id == task_id)) is None
    reopened.dispose()


def test_status_visual_mapping_covers_every_status():
    assert set(STATUS_COLOR_TOKEN) == set(TaskStatus)
    assert all(status_color(DARK_THEME, status).startswith("#") for status in TaskStatus)
