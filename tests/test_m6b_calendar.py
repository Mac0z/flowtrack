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
from flowtrack.ui.widgets.calendar_grid import CalendarMode, OVERFLOW_ROLE, month_start, week_start
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox


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


def test_calendar_placement_uses_due_date_only(application):
    service, queries, _projects = make_services()
    due = date(2026, 9, 10)
    due_task = service.create_task("Due task", start_date=due - timedelta(days=3), due_date=due)
    start_only = service.create_task("Start only", start_date=due)
    view = CalendarView(service, queries)
    view.anchor = month_start(due)
    view.refresh()
    assert due_task in ids(view.grid.cells[due])
    assert start_only not in ids(view.grid.cells[due])
    assert start_only in ids(view.unscheduled)


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


def test_real_confirmation_result_defaults_to_ok_and_persists(application, monkeypatch):
    service, queries, _projects = make_services()
    old = date.today(); new = old + timedelta(days=1)
    task_id = service.create_task("Really move", due_date=old)
    view = CalendarView(service, queries)

    def accept(dialog):
        assert dialog.standardButton(dialog.defaultButton()) == QMessageBox.StandardButton.Ok
        assert dialog.standardButton(dialog.escapeButton()) == QMessageBox.StandardButton.Cancel
        return QMessageBox.StandardButton.Ok.value

    monkeypatch.setattr(QMessageBox, "exec", accept)
    assert view.request_date_change(task_id, new)
    assert queries.task_detail(task_id)["due_date"] == new
    assert task_id not in ids(view.grid.cells[old])
    assert task_id in ids(view.grid.cells[new])


def test_real_confirmation_cancel_does_not_persist(application, monkeypatch):
    service, queries, _projects = make_services()
    old = date.today(); task_id = service.create_task("Do not move", due_date=old)
    view = CalendarView(service, queries)
    monkeypatch.setattr(QMessageBox, "exec", lambda _dialog: QMessageBox.StandardButton.Cancel.value)
    assert not view.request_date_change(task_id, old + timedelta(days=1))
    assert queries.task_detail(task_id)["due_date"] == old


def test_unscheduled_confirmed_move_is_immediately_visible(application, monkeypatch):
    service, queries, _projects = make_services()
    target = date.today(); task_id = service.create_task("Schedule me")
    view = CalendarView(service, queries)
    monkeypatch.setattr(QMessageBox, "exec", lambda _dialog: QMessageBox.StandardButton.Ok.value)
    assert view.request_date_change(task_id, target)
    assert task_id not in ids(view.unscheduled)
    assert task_id in ids(view.grid.cells[target])


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


def test_refresh_and_new_view_load_new_due_task(application):
    service, queries, _projects = make_services()
    due = date.today()
    view = CalendarView(service, queries)
    task_id = service.create_task("Created while calendar is open", due_date=due)
    view.refresh()
    assert task_id in ids(view.grid.cells[due])
    restarted_view = CalendarView(service, queries)
    assert task_id in ids(restarted_view.grid.cells[due])


def test_task_chips_follow_viewport_and_disable_horizontal_scrollbars(application):
    service, queries, _projects = make_services()
    due = date.today(); service.create_task("A readable task title", due_date=due)
    view = CalendarView(service, queries)
    view.resize(1000, 700); view.show(); application.processEvents()
    for task_list in (view.grid.cells[due], view.unscheduled):
        assert task_list.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    day_list = view.grid.cells[due]
    item = day_list.item(0); chip = day_list.itemWidget(item)
    assert item.sizeHint().width() > 0
    assert chip.width() == max(1, day_list.viewport().width() - 2)


def test_month_overflow_exposes_real_ids_and_activation(application):
    service, queries, _projects = make_services()
    due = date.today()
    task_ids = [service.create_task(f"Task {index}", due_date=due) for index in range(5)]
    view = CalendarView(service, queries)
    day_list = view.grid.cells[due]
    assert day_list.count() == 4
    direct_ids = set(ids(day_list)[:3])
    assert len(direct_ids) == 3
    more = day_list.item(3)
    assert more.text() == "+2 more" and more.data(OVERFLOW_ROLE) == due
    day_list.itemClicked.emit(more)
    application.processEvents()
    dialog = view.grid.overflow_dialogs[due]
    assert set(dialog.task_ids) == set(task_ids) - direct_ids
    opened = []
    view.task_selected.connect(opened.append)
    activated_id = dialog.task_ids[1]
    dialog.task_list.itemDoubleClicked.emit(dialog.task_list.item(1))
    assert opened == [activated_id]


def test_up_to_three_month_tasks_render_without_overflow(application):
    service, queries, _projects = make_services()
    due = date.today()
    expected = {service.create_task(f"Visible {index}", due_date=due) for index in range(3)}
    view = CalendarView(service, queries)
    day_list = view.grid.cells[due]
    assert day_list.count() == 3
    assert set(ids(day_list)) == expected
    assert all(day_list.item(index).data(OVERFLOW_ROLE) is None for index in range(3))


def test_calendar_introduces_no_schema_migration():
    from pathlib import Path
    migrations = list(Path("flowtrack/persistence/migrations/versions").glob("*.py"))
    assert {path.name for path in migrations} == {"0001_initial_schema.py", "__init__.py"}
