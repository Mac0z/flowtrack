"""Focused coverage for the M9C inspector-save diagnostic boundaries."""

import json

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("PySide6")

from sqlalchemy import create_engine, select

from flowtrack.application import TaskExecutionService, TaskQueryService
from flowtrack.application.projects import ProjectService
from flowtrack.infrastructure.performance import DIAGNOSTICS_FILENAME, PerformanceDiagnostics, read_events
from flowtrack.persistence.database import session_factory
from flowtrack.persistence.models import Base, Task
from flowtrack.ui.widgets.task_inspector import TaskInspector
from flowtrack.ui.navigation import Destination
from flowtrack.ui.windows.main_window import MainWindow


def _services(performance):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    return TaskExecutionService(factory, performance), TaskQueryService(factory), factory


def test_inspector_load_and_save_emit_all_boundaries_and_resume_event(application, tmp_path):
    performance = PerformanceDiagnostics(True, directory=tmp_path)
    commands, queries, _ = _services(performance)
    project_id = ProjectService(commands._factory).create_project("not recorded")
    task_id = commands.create_task("private title", project_id=project_id)
    inspector = TaskInspector(commands, queries, performance=performance)
    inspector.load_task(task_id)
    handled = []
    inspector.saved.connect(lambda: handled.append("synchronous"))

    inspector.save()
    assert handled == ["synchronous"]
    application.processEvents()

    events = read_events(performance.retained_paths())
    names = [event["event"] for event in events]
    for name in (
        "inspector_save.total", "inspector_save.emit_refresh",
        "ui_event_loop.resume_after_save", "inspector_load.total",
        "inspector_load.task_detail", "inspector_load.owners", "inspector_load.tags",
        "inspector_load.dependencies", "inspector_load.widget_population",
    ):
        assert name in names
    save_events = [event for event in events if event["event"].startswith("inspector_save.")]
    assert all(event["context"]["has_project"] is True for event in save_events)


def test_disabled_new_measurements_create_no_events(application, tmp_path):
    performance = PerformanceDiagnostics(False, directory=tmp_path)
    commands, queries, _ = _services(performance)
    task_id = commands.create_task("private")
    inspector = TaskInspector(commands, queries, performance=performance)
    inspector.load_task(task_id)
    inspector.save()
    application.processEvents()
    assert not performance.retained_paths()


def test_diagnostics_write_failure_cannot_break_inspector_save(application, tmp_path):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("blocked")
    performance = PerformanceDiagnostics(True, directory=blocked)
    commands, queries, factory = _services(performance)
    task_id = commands.create_task("before")
    inspector = TaskInspector(commands, queries, performance=performance)
    inspector.load_task(task_id)
    inspector.title.setText("after")
    inspector.save()
    application.processEvents()
    with factory() as session:
        assert session.scalar(select(Task.title).where(Task.id == task_id)) == "after"


def test_new_event_context_rejects_identifiers_and_arbitrary_strings(tmp_path):
    performance = PerformanceDiagnostics(True, directory=tmp_path)
    performance.record("inspector_save.total", 1, context={
        "has_project": True, "task_id": "secret-id", "project_id": "secret-project",
        "task_name": "secret title", "status": "not-a-real-status",
    })
    event = json.loads((tmp_path / DIAGNOSTICS_FILENAME).read_text())
    assert event["context"] == {"has_project": True}
    assert "secret" not in json.dumps(event)


def test_main_window_refreshes_emit_total_and_component_metrics(application, tmp_path):
    performance = PerformanceDiagnostics(True, directory=tmp_path)
    commands, queries, _ = _services(performance)
    window = MainWindow(task_service=commands, task_queries=queries, performance=performance)
    window.navigate(Destination.PROJECTS)
    window.refresh_project_views()

    names = [event["event"] for event in read_events(performance.retained_paths())]
    assert "ui_refresh.project_views_total" in names
    assert "ui_refresh.execution_views_total" in names
    assert "ui_refresh.project" in names
    assert "ui_refresh.pinned_projects" in names

    task_id = commands.create_task("private")
    window.open_inspector(task_id)
    window.refresh_execution_views()
    inspector_refresh_count = sum(
        event["event"] == "ui_refresh.inspector"
        for event in read_events(performance.retained_paths())
    )
    assert inspector_refresh_count == 1

    window.inspector.close_inspector()
    window.refresh_execution_views()
    assert sum(
        event["event"] == "ui_refresh.inspector"
        for event in read_events(performance.retained_paths())
    ) == inspector_refresh_count
    window.close()


def test_opening_multiple_tasks_does_not_duplicate_saved_refresh(application, tmp_path):
    performance = PerformanceDiagnostics(True, directory=tmp_path)
    commands, queries, _ = _services(performance)
    window = MainWindow(task_service=commands, task_queries=queries, performance=performance)
    first = commands.create_task("first")
    second = commands.create_task("second")
    window.open_inspector(first)
    window.open_inspector(second)

    before = sum(
        event["event"] == "ui_refresh.project_views_total"
        for event in read_events(performance.retained_paths())
    )
    window.inspector.saved.emit()
    after = sum(
        event["event"] == "ui_refresh.project_views_total"
        for event in read_events(performance.retained_paths())
    )

    assert after == before + 1
    window.close()
