"""Regressions for the M5 tab theme and post-capture refresh path."""

from datetime import date
from pathlib import Path

from PySide6.QtCore import QSettings
from sqlalchemy import create_engine

from flowtrack.application.task_execution import TaskExecutionService
from flowtrack.application.task_queries import TaskQueryService
from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.persistence.database import session_factory
from flowtrack.persistence.models import Base
from flowtrack.ui.navigation import Destination
from flowtrack.ui.theme.dark import DARK_THEME
from flowtrack.ui.theme.stylesheet import build_stylesheet
from flowtrack.ui.views.dashboard import DashboardView
from flowtrack.ui.views.my_tasks import MyTasksView
from flowtrack.ui.views.projects import ProjectsView
from flowtrack.ui.windows.main_window import MainWindow


def _window(tmp_path) -> MainWindow:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    settings = ApplicationSettings(
        QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    )
    return MainWindow(
        settings,
        TaskExecutionService(factory),
        TaskQueryService(factory),
    )


def test_selected_data_directory_persists_without_requiring_existing_path(tmp_path) -> None:
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings = ApplicationSettings(store)
    selected = tmp_path / "not-created-yet" / "FlowTrackData"
    settings.data_directory = selected

    reopened = ApplicationSettings(
        QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    )
    assert reopened.data_directory == Path(selected)


def test_stylesheet_defines_semantic_tab_states() -> None:
    stylesheet = build_stylesheet(DARK_THEME)
    colors = DARK_THEME.colors

    assert "QTabWidget::pane" in stylesheet
    assert "QTabBar::tab {" in stylesheet
    assert "QTabBar::tab:selected" in stylesheet
    assert "QTabBar::tab:hover:!selected" in stylesheet
    assert "QTabBar::tab:disabled" in stylesheet
    assert f"background: {colors.surface_secondary}" in stylesheet
    assert f"color: {colors.text_secondary}" in stylesheet
    assert f"background: {colors.surface_selected}" in stylesheet
    assert f"border-bottom: 2px solid {colors.accent}" in stylesheet


def test_project_capture_immediately_refreshes_project_my_tasks_and_dashboard(
    application, tmp_path
) -> None:
    window = _window(tmp_path)
    project_id = window.project_service.create_project("Launch")
    window.open_project(project_id)

    window.open_project_task(project_id)
    window.quick_capture.title_edit.setText("Prepare launch notes")
    window.quick_capture.start_edit.set_date_or_none(date.today())
    window.quick_capture.due_edit.set_date_or_none(date.today())
    window.quick_capture.submit()

    projects = window.pages[Destination.PROJECTS]
    my_tasks = window.pages[Destination.MY_TASKS]
    dashboard = window.pages[Destination.DASHBOARD]
    assert isinstance(projects, ProjectsView)
    assert isinstance(my_tasks, MyTasksView)
    assert isinstance(dashboard, DashboardView)
    assert projects.table.rowCount() == 1
    assert projects.table.item(0, 0).text() == "Prepare launch notes"
    assert [my_tasks.table.item(row, 1).text() for row in range(my_tasks.table.rowCount())] == [
        "Prepare launch notes"
    ]
    assert dashboard.task_table.rowCount() == 1
    assert dashboard.task_table.item(0, 0).text() == "Prepare launch notes"
    window.close()


def test_reopening_capture_does_not_duplicate_effective_refreshes(
    application, tmp_path, monkeypatch
) -> None:
    window = _window(tmp_path)
    projects = window.pages[Destination.PROJECTS]
    my_tasks = window.pages[Destination.MY_TASKS]
    dashboard = window.pages[Destination.DASHBOARD]
    assert isinstance(projects, ProjectsView)
    assert isinstance(my_tasks, MyTasksView)
    assert isinstance(dashboard, DashboardView)
    refreshes = {"projects": 0, "my_tasks": 0, "dashboard": 0, "pinned": 0}

    def count(name):
        return lambda *_: refreshes.__setitem__(name, refreshes[name] + 1)

    monkeypatch.setattr(projects, "refresh", count("projects"))
    monkeypatch.setattr(my_tasks, "refresh", count("my_tasks"))
    monkeypatch.setattr(dashboard, "refresh", count("dashboard"))
    monkeypatch.setattr(window, "refresh_pinned_projects", count("pinned"))

    window.open_quick_task()
    window.quick_capture.reject()
    window.open_quick_task()
    window.quick_capture.reject()
    window.open_project_task(window.project_service.create_project("One"))
    window.quick_capture.reject()
    window.quick_capture.task_created.emit(object())

    assert refreshes == {"projects": 1, "my_tasks": 1, "dashboard": 1, "pinned": 1}
    window.close()
