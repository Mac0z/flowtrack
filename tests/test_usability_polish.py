"""Focused coverage for dialog surfaces and My Tasks lifecycle scopes."""
from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings, Qt
from sqlalchemy import create_engine

from flowtrack.application import MyTasksScope, TaskExecutionService, TaskFilters, TaskQueryService
from flowtrack.domain.enums import TaskPriority, TaskStatus
from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.persistence.database import session_factory
from flowtrack.persistence.models import Base
from flowtrack.ui.theme.dark import DARK_THEME
from flowtrack.ui.theme.stylesheet import build_stylesheet
from flowtrack.ui.views.my_tasks import MyTasksView


@pytest.fixture
def execution_view(application, tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    service, queries = TaskExecutionService(factory), TaskQueryService(factory)
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    return MyTasksView(service, queries, ApplicationSettings(store)), service, queries


def _titles(view: MyTasksView) -> list[str]:
    return [view.table.item(row, 1).text().strip() for row in range(view.table.rowCount())]


def test_dialog_labels_are_transparent_but_inputs_keep_token_surface() -> None:
    stylesheet = build_stylesheet(DARK_THEME)
    assert "QDialog QLabel { background: transparent; }" in stylesheet
    assert f"QLineEdit {{ background: {DARK_THEME.colors.surface_secondary};" in stylesheet
    assert f"QComboBox, QDateEdit, QPlainTextEdit, QSpinBox {{ background: {DARK_THEME.colors.surface_secondary};" in stylesheet


def test_my_tasks_defaults_to_active_and_separates_lifecycle_states(execution_view) -> None:
    view, service, _ = execution_view
    service.create_task("Active")
    complete = service.create_task("Complete")
    cancelled = service.create_task("Cancelled")
    service.complete_task(complete); service.cancel_task(cancelled)
    view.refresh()
    assert view.scope is MyTasksScope.ACTIVE
    assert _titles(view) == ["Active"]
    view.scope_tabs.setCurrentIndex(1)
    assert set(_titles(view)) == {"Complete", "Cancelled"}


def test_status_changes_move_tasks_between_scopes_immediately(execution_view) -> None:
    view, service, _ = execution_view
    task_id = service.create_task("Moving")
    view.refresh(); assert _titles(view) == ["Moving"]
    view._clicked(0, 0)
    assert _titles(view) == []
    view.scope_tabs.setCurrentIndex(1)
    assert _titles(view) == ["Moving"]
    service.update_task(task_id, status=TaskStatus.WAITING)
    view.refresh(); assert _titles(view) == []
    view.scope_tabs.setCurrentIndex(0)
    assert _titles(view) == ["Moving"]


def test_existing_filters_and_activation_work_in_each_scope(execution_view) -> None:
    view, service, _ = execution_view
    service.create_task("Active match", priority=TaskPriority.CRITICAL, due_date=date.today())
    service.create_task("Active other")
    historical = service.create_task("Historic match", priority=TaskPriority.CRITICAL)
    service.complete_task(historical)
    activated: list[object] = []
    view.task_selected.connect(activated.append)
    view.priority.setCurrentIndex(view.priority.findData(TaskPriority.CRITICAL.value))
    view.search.setText("match")
    assert _titles(view) == ["Active match"]
    view._activate_task(0, 1)
    assert activated
    view.scope_tabs.setCurrentIndex(1)
    assert _titles(view) == ["Historic match"]
    view._activate_task(0, 1)
    assert activated[-1] == historical
    assert set(view.status.itemData(i) for i in range(1, view.status.count())) == {
        TaskStatus.COMPLETE.value, TaskStatus.CANCELLED.value,
    }


def test_query_scope_is_a_higher_level_filter(execution_view) -> None:
    _, service, queries = execution_view
    service.create_task("Waiting", priority=TaskPriority.HIGH)
    complete = service.create_task("Done", priority=TaskPriority.HIGH)
    service.complete_task(complete)
    active = queries.my_tasks(filters=TaskFilters(
        statuses=MyTasksScope.ACTIVE.statuses,
        priorities=frozenset({TaskPriority.HIGH}),
    ))
    history = queries.my_tasks(filters=TaskFilters(
        statuses=MyTasksScope.HISTORY.statuses,
        priorities=frozenset({TaskPriority.HIGH}),
    ))
    assert [row.title for row in active] == ["Waiting"]
    assert [row.title for row in history] == ["Done"]
