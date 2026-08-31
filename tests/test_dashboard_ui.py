"""Focused regressions for the Dashboard presentation."""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from flowtrack.ui.views.dashboard import DashboardView
from flowtrack.ui.widgets import ProgressDisplay


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


def test_dashboard_task_row_is_sized_for_complete_content(application):
    task_id = uuid4()
    dashboard = DashboardView(_DashboardQueries(task_id))

    item = dashboard.task_list.item(0)
    row_widget = dashboard.task_list.itemWidget(item)
    assert row_widget is not None

    labels = row_widget.findChildren(QLabel)
    progress_displays = row_widget.findChildren(ProgressDisplay)

    assert item.data(Qt.ItemDataRole.UserRole) == task_id
    assert any("Prepare project update" in label.text() for label in labels)
    assert len(progress_displays) == 1
    assert item.sizeHint().height() >= dashboard.TASK_ROW_MINIMUM_HEIGHT
    assert item.sizeHint().height() >= row_widget.sizeHint().height()


def test_dashboard_selected_task_row_keeps_item_highlight_visible(application):
    first_task_id = uuid4()
    second_task_id = uuid4()
    dashboard = DashboardView(_DashboardQueries(first_task_id, second_task_id))

    second_item = dashboard.task_list.item(1)
    dashboard.task_list.setCurrentItem(second_item)
    row_widget = dashboard.task_list.itemWidget(second_item)

    assert dashboard.task_list.currentItem() is second_item
    assert second_item.isSelected()
    assert second_item.data(Qt.ItemDataRole.UserRole) == second_task_id
    assert row_widget is not None
    assert row_widget.objectName() == "dashboardTaskRow"
    assert "QWidget#dashboardTaskRow" in application.styleSheet()
    assert "QWidget#dashboardTaskRow QLabel { background: transparent; }" in application.styleSheet()
    assert len(row_widget.findChildren(ProgressDisplay)) == 1
