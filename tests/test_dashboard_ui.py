"""Focused regressions for the Dashboard presentation."""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from PySide6.QtCore import Qt
from flowtrack.ui.views.dashboard import DashboardView
from flowtrack.ui.widgets import ProgressCell, ProgressDisplay


class _DashboardQueries:
    def __init__(self, *task_ids) -> None:
        self.task_ids = task_ids

    def dashboard(self):
        tasks = tuple(
            SimpleNamespace(
                id=task_id,
                title=f"Prepare project update {index}",
                due_date=date(2026, 9, 2),
                progress=45,
            )
            for index, task_id in enumerate(self.task_ids, start=1)
        )
        return SimpleNamespace(
            active_projects=1,
            in_progress=1,
            completed=0,
            overdue=0,
            due_this_week=tasks,
            projects=(),
            pinned_projects=(),
        )


def test_dashboard_table_displays_compact_task_data(application):
    task_id = uuid4()
    dashboard = DashboardView(_DashboardQueries(task_id))

    assert dashboard.task_table.rowCount() == 1
    assert dashboard.task_table.item(0, 0).text() == "Prepare project update 1"
    assert dashboard.task_table.item(0, 1).text() == "Wed 02 Sep"
    progress_cell = dashboard.task_table.cellWidget(0, 2)
    assert isinstance(progress_cell, ProgressCell)
    assert progress_cell.progress_display.value() == 45
    assert dashboard.task_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == str(task_id)
    assert dashboard.task_table.verticalHeader().defaultSectionSize() == dashboard.TASK_ROW_MINIMUM_HEIGHT
    assert dashboard.task_table.editTriggers() == dashboard.task_table.EditTrigger.NoEditTriggers


def test_progress_cell_centres_compact_display_without_intercepting_selection(application):
    cell = ProgressCell(45)
    progress = cell.progress_display

    assert isinstance(progress, ProgressDisplay)
    assert progress.parent() is cell
    assert progress.maximumHeight() == 18
    assert cell.layout().alignmentOf(progress) & Qt.AlignmentFlag.AlignVCenter
    assert cell.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_dashboard_selection_and_activation_use_normal_full_rows(application):
    first_task_id = uuid4()
    second_task_id = uuid4()
    dashboard = DashboardView(_DashboardQueries(first_task_id, second_task_id))

    dashboard.task_table.selectRow(1)
    selected = dashboard.task_table.selectionModel().selectedRows()
    assert [index.row() for index in selected] == [1]
    assert all(dashboard.task_table.item(1, column).isSelected() for column in range(3))
    assert dashboard.task_table.item(1, 0).data(Qt.ItemDataRole.UserRole) == str(second_task_id)

    activated = []
    dashboard.task_selected.connect(activated.append)
    dashboard._activate_task(1, 2)
    assert activated == [second_task_id]


def test_dashboard_empty_state_replaces_empty_table(application):
    dashboard = DashboardView(_DashboardQueries())
    assert dashboard.task_table.rowCount() == 0
    assert dashboard.task_table.isHidden()
    assert not dashboard.empty.isHidden()
