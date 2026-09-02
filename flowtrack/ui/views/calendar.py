"""Month/week task planning calendar."""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget
from sqlalchemy.exc import SQLAlchemyError

from flowtrack.application.task_execution import TaskExecutionService
from flowtrack.application.task_queries import MyTasksScope, TaskFilters, TaskQueryService, TaskRow
from flowtrack.domain.enums import TaskPriority, TaskStatus
from flowtrack.ui.widgets.calendar_grid import CalendarGrid, CalendarMode, CalendarTaskList, add_task_item, month_start, week_start


class CalendarView(QWidget):
    """Planning surface backed exclusively by task query and execution services."""

    task_selected = Signal(object)
    data_changed = Signal()

    def __init__(self, task_service: TaskExecutionService, queries: TaskQueryService, parent=None) -> None:
        super().__init__(parent)
        self.task_service, self.queries = task_service, queries
        self.mode = CalendarMode.MONTH
        self.anchor = month_start(date.today())
        self._rows: list[TaskRow] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("Calendar")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        self.month_button = QPushButton("Month")
        self.week_button = QPushButton("Week")
        self.month_button.clicked.connect(lambda: self.set_mode(CalendarMode.MONTH))
        self.week_button.clicked.connect(lambda: self.set_mode(CalendarMode.WEEK))
        header.addWidget(self.month_button); header.addWidget(self.week_button)
        root.addLayout(header)
        navigation = QHBoxLayout()
        self.previous_button = QPushButton("‹")
        self.next_button = QPushButton("›")
        self.today_button = QPushButton("Today")
        self.previous_button.clicked.connect(self.previous_period)
        self.next_button.clicked.connect(self.next_period)
        self.today_button.clicked.connect(self.go_to_today)
        navigation.addWidget(self.previous_button); navigation.addWidget(self.next_button); navigation.addWidget(self.today_button)
        self.period_heading = QLabel()
        self.period_heading.setObjectName("sectionTitle")
        navigation.addWidget(self.period_heading); navigation.addStretch()
        root.addLayout(navigation)
        filters = QHBoxLayout()
        self.project_filter = QComboBox(); self.owner_filter = QComboBox(); self.status_filter = QComboBox(); self.priority_filter = QComboBox()
        for label, combo in (("Project", self.project_filter), ("Owner", self.owner_filter), ("Status", self.status_filter), ("Priority", self.priority_filter)):
            combo.setAccessibleName(label); combo.currentIndexChanged.connect(self.refresh); filters.addWidget(combo)
        self.show_history = QCheckBox("Show completed/cancelled")
        self.show_history.toggled.connect(self.refresh); filters.addWidget(self.show_history); filters.addStretch()
        root.addLayout(filters)
        content = QHBoxLayout()
        self.grid = CalendarGrid(self.request_date_change)
        self.grid.task_activated.connect(self.task_selected)
        content.addWidget(self.grid, 1)
        unscheduled_panel = QFrame(); unscheduled_panel.setObjectName("panel"); unscheduled_panel.setFixedWidth(220)
        unscheduled_layout = QVBoxLayout(unscheduled_panel)
        unscheduled_layout.addWidget(QLabel("Unscheduled"))
        hint = QLabel("Drag a task onto a date to schedule it."); hint.setWordWrap(True); hint.setObjectName("mutedText"); unscheduled_layout.addWidget(hint)
        self.unscheduled = CalendarTaskList(None, self.request_date_change)
        self.unscheduled.task_activated.connect(self.task_selected); unscheduled_layout.addWidget(self.unscheduled, 1)
        content.addWidget(unscheduled_panel)
        root.addLayout(content, 1)
        self.error = QLabel(); self.error.setObjectName("dangerText"); self.error.setWordWrap(True); self.error.hide(); root.addWidget(self.error)
        self._populate_filters()
        self.refresh()

    def _populate_filters(self) -> None:
        for combo, values in ((self.project_filter, self.queries.projects()), (self.owner_filter, [(item[0], item[1]) for item in self.queries.owners()])):
            combo.blockSignals(True); combo.addItem("All", None)
            for identifier, name in values: combo.addItem(name, identifier)
            combo.blockSignals(False)
        self.status_filter.blockSignals(True); self.status_filter.addItem("All statuses", None)
        for value in TaskStatus: self.status_filter.addItem(value.value.replace("_", " ").title(), value)
        self.status_filter.blockSignals(False)
        self.priority_filter.blockSignals(True); self.priority_filter.addItem("All priorities", None)
        for value in TaskPriority: self.priority_filter.addItem(value.value.title(), value)
        self.priority_filter.blockSignals(False)

    def _filters(self) -> TaskFilters:
        selected_status = self.status_filter.currentData()
        statuses = frozenset({selected_status}) if selected_status else (
            frozenset(TaskStatus) if self.show_history.isChecked() else MyTasksScope.ACTIVE.statuses
        )
        selected_priority = self.priority_filter.currentData()
        return TaskFilters(statuses=statuses, priorities=frozenset({selected_priority}) if selected_priority else frozenset(),
                           project_id=self.project_filter.currentData(), owner_id=self.owner_filter.currentData())

    def refresh(self, *_args) -> None:
        self._rows = self.queries.my_tasks(filters=self._filters())
        self.grid.render(self._rows, anchor=self.anchor, mode=self.mode)
        self.unscheduled.clear()
        for task in (row for row in self._rows if row.due_date is None):
            add_task_item(self.unscheduled, task, roomy=True)
        self._update_heading()

    def _update_heading(self) -> None:
        if self.mode is CalendarMode.MONTH:
            self.period_heading.setText(self.anchor.strftime("%B %Y"))
        else:
            start = week_start(self.anchor); end = start + timedelta(days=6)
            self.period_heading.setText(f"{start:%d %b} – {end:%d %b %Y}")
        self.month_button.setEnabled(self.mode is not CalendarMode.MONTH)
        self.week_button.setEnabled(self.mode is not CalendarMode.WEEK)

    def set_mode(self, mode: CalendarMode) -> None:
        self.mode = mode
        self.anchor = month_start(self.anchor) if mode is CalendarMode.MONTH else week_start(self.anchor)
        self.refresh()

    def previous_period(self) -> None:
        if self.mode is CalendarMode.WEEK: self.anchor -= timedelta(days=7)
        else: self.anchor = (self.anchor - timedelta(days=1)).replace(day=1)
        self.refresh()

    def next_period(self) -> None:
        if self.mode is CalendarMode.WEEK: self.anchor += timedelta(days=7)
        else: self.anchor = (self.anchor.replace(day=28) + timedelta(days=4)).replace(day=1)
        self.refresh()

    def go_to_today(self) -> None:
        self.anchor = month_start(date.today()) if self.mode is CalendarMode.MONTH else week_start(date.today())
        self.refresh()

    def confirm_date_change(self, task: TaskRow, new_date: date) -> bool:
        dialog = QMessageBox(QMessageBox.Icon.Question, "Move task due date?",
                             f"Move {task.title} due date to {new_date:%d %b %Y}?", parent=self)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(QMessageBox.StandardButton.Ok)
        dialog.setEscapeButton(QMessageBox.StandardButton.Cancel)
        return QMessageBox.StandardButton(dialog.exec()) == QMessageBox.StandardButton.Ok

    def request_date_change(self, task_id: UUID, new_date: date) -> bool:
        task = next((row for row in self._rows if row.id == task_id), None)
        if task is None or task.due_date == new_date or not self.confirm_date_change(task, new_date):
            self.refresh()
            return False
        try:
            self.task_service.update_task(task_id, due_date=new_date)
        except (ValueError, RuntimeError, SQLAlchemyError) as exc:
            self.error.setText(f"Could not change due date: {exc}")
            self.error.show(); self.refresh()
            return False
        self.error.hide(); self.refresh(); self.data_changed.emit()
        return True
