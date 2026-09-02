"""Focused, non-pixel tests for the M6B planning calendar."""
import os
from datetime import date, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import create_engine

from flowtrack.application.projects import ProjectService
from flowtrack.application.task_execution import TaskExecutionService
from flowtrack.application.task_queries import TaskQueryService
from flowtrack.domain.enums import TaskPriority, TaskStatus
from flowtrack.persistence.database import session_factory
from flowtrack.persistence.models import Base
from flowtrack.ui.views.calendar import CalendarView
from flowtrack.ui.widgets.calendar_grid import CalendarMode, month_start, week_start


def make_services():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    return TaskExecutionService(factory), TaskQueryService(factory), ProjectService(factory)


def ids(task_list):
    return [task_list.item(index).data(256) for index in range(task_list.count())]


def test_month_and_week_show_same_task_on_due_date(application):
    service, queries, _projects = make_services()
    due = date(2026, 9, 16)
    task_id = service.create_task("Calendar work", due_date=due)
    view = CalendarView(service, queries)
    view.anchor = month_start(due); view.refresh()
    assert task_id in ids(view.grid.cells[due])
    view.set_mode(CalendarMode.WEEK); view.anchor = week_start(due); view.refresh()
    assert task_id in ids(view.grid.cells[due])


def test_unscheduled_and_history_default_visibility(application):
    service, queries, _projects = make_services()
    active = service.create_task("Unscheduled")
    completed = service.create_task("Done")
    service.update_task(completed, status=TaskStatus.COMPLETE)
    view = CalendarView(service, queries)
    assert active in ids(view.unscheduled)
    assert completed not in ids(view.unscheduled)
    view.show_history.setChecked(True)
    assert completed in ids(view.unscheduled)


def test_activation_emits_task_identifier(application):
    service, queries, _projects = make_services()
    due = date.today(); task_id = service.create_task("Open me", due_date=due)
    view = CalendarView(service, queries); opened = []
    view.task_selected.connect(opened.append)
    item = view.grid.cells[due].item(0)
    view.grid.cells[due].itemDoubleClicked.emit(item)
    assert opened == [task_id]


def test_confirmed_date_move_uses_service_refreshes_and_emits(application, monkeypatch):
    service, queries, _projects = make_services()
    old = date.today(); new = old + timedelta(days=2)
    task_id = service.create_task("Move me", due_date=old)
    view = CalendarView(service, queries); calls = []; changed = []
    original = service.update_task
    monkeypatch.setattr(view, "confirm_date_change", lambda *_: True)
    monkeypatch.setattr(service, "update_task", lambda identifier, **changes: (calls.append((identifier, changes)), original(identifier, **changes))[1])
    view.data_changed.connect(lambda: changed.append(True))
    assert view.request_date_change(task_id, new)
    assert calls == [(task_id, {"due_date": new})]
    assert changed == [True]
    assert task_id not in ids(view.grid.cells[old]) and task_id in ids(view.grid.cells[new])


def test_cancelled_date_move_does_not_persist(application, monkeypatch):
    service, queries, _projects = make_services()
    old = date.today(); task_id = service.create_task("Stay", due_date=old)
    view = CalendarView(service, queries); calls = []
    monkeypatch.setattr(view, "confirm_date_change", lambda *_: False)
    monkeypatch.setattr(service, "update_task", lambda *args, **kwargs: calls.append((args, kwargs)))
    assert not view.request_date_change(task_id, old + timedelta(days=1))
    assert calls == [] and task_id in ids(view.grid.cells[old])


def test_failed_date_move_restores_original_date(application, monkeypatch):
    service, queries, _projects = make_services()
    old = date.today(); task_id = service.create_task("Stay safe", due_date=old)
    view = CalendarView(service, queries)
    monkeypatch.setattr(view, "confirm_date_change", lambda *_: True)
    monkeypatch.setattr(service, "update_task", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("disk full")))
    assert not view.request_date_change(task_id, old + timedelta(days=1))
    assert task_id in ids(view.grid.cells[old])
    assert not view.error.isHidden()


def test_today_and_period_navigation(application):
    service, queries, _projects = make_services(); view = CalendarView(service, queries)
    view.anchor = date(2026, 6, 1); view.next_period()
    assert view.anchor == date(2026, 7, 1)
    view.previous_period(); assert view.anchor == date(2026, 6, 1)
    view.go_to_today(); assert view.anchor == month_start(date.today())
    view.set_mode(CalendarMode.WEEK); start = view.anchor
    view.next_period(); assert view.anchor == start + timedelta(days=7)


def test_project_owner_status_and_priority_filters(application):
    service, queries, projects = make_services()
    project = projects.create_project("Filtered project")
    owner = service.create_owner("Avery")
    wanted = service.create_task("Wanted", project_id=project, owner_id=owner, priority=TaskPriority.HIGH)
    service.update_task(wanted, status=TaskStatus.BLOCKED)
    service.create_task("Other")
    view = CalendarView(service, queries)
    view.project_filter.setCurrentIndex(view.project_filter.findData(project))
    view.owner_filter.setCurrentIndex(view.owner_filter.findData(owner))
    view.status_filter.setCurrentIndex(view.status_filter.findData(TaskStatus.BLOCKED))
    view.priority_filter.setCurrentIndex(view.priority_filter.findData(TaskPriority.HIGH))
    assert ids(view.unscheduled) == [wanted]


def test_calendar_introduces_no_schema_migration():
    from pathlib import Path
    migrations = list(Path("flowtrack/persistence/migrations/versions").glob("*.py"))
    assert {path.name for path in migrations} == {"0001_initial_schema.py", "__init__.py"}
