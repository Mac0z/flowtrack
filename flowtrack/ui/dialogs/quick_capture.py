"""Compact M4 quick task capture dialog."""

from datetime import date, timedelta
from uuid import UUID

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit

from flowtrack.application.task_execution import TaskExecutionService, TaskValidationError
from flowtrack.application.task_queries import TaskQueryService
from flowtrack.domain.enums import TaskPriority
from flowtrack.ui.widgets.nullable_date_edit import NullableDateEdit


class QuickCaptureDialog(QDialog):
    task_created = Signal(object)

    def __init__(self, service: TaskExecutionService, queries: TaskQueryService, parent=None) -> None:
        super().__init__(parent)
        self.service, self.queries = service, queries
        self.setWindowTitle("Quick Add Task")
        self.setMinimumWidth(430)
        form = QFormLayout(self)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("What needs doing?")
        self.project_combo, self.owner_combo, self.priority_combo = QComboBox(), QComboBox(), QComboBox()
        self.project_combo.addItem("No project", None)
        self.owner_combo.addItem("Unassigned", None)
        for value in TaskPriority:
            self.priority_combo.addItem(value.value.replace("_", " ").title(), value.value)
        self.priority_combo.setCurrentIndex(list(TaskPriority).index(TaskPriority.MEDIUM))
        self.start_edit = NullableDateEdit()
        self.due_edit = NullableDateEdit("No due date")
        self.error_label = QLabel()
        self.error_label.setObjectName("dangerText")
        for label, widget in (("Title", self.title_edit), ("Project", self.project_combo),
                              ("Owner", self.owner_combo), ("Start", self.start_edit),
                              ("Due", self.due_edit), ("Priority", self.priority_combo)):
            form.addRow(label, widget)
        form.addRow(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons)
        buttons.accepted.connect(self.submit)
        buttons.rejected.connect(self.reject)
        self.title_edit.returnPressed.connect(self.submit)
        self.refresh_options()
        self.reset_default_dates()

    def reset_default_dates(self) -> None:
        today = date.today()
        self.start_edit.set_date_or_none(today)
        self.due_edit.set_date_or_none(today + timedelta(days=1))

    def refresh_options(self) -> None:
        while self.project_combo.count() > 1:
            self.project_combo.removeItem(1)
        while self.owner_combo.count() > 1:
            self.owner_combo.removeItem(1)
        for project_id, name in self.queries.projects():
            self.project_combo.addItem(name, str(project_id))
        for owner_id, name, _ in self.queries.owners(True):
            self.owner_combo.addItem(name, str(owner_id))

    def open(self) -> None:
        self.refresh_options()
        self.reset_default_dates()
        self.error_label.clear()
        super().open()
        self.title_edit.setFocus()

    def open_for_project(self, project_id: UUID) -> None:
        """Open capture with the owning project already selected."""
        self.open()
        index = self.project_combo.findData(str(project_id))
        if index >= 0:
            self.project_combo.setCurrentIndex(index)

    def submit(self) -> None:
        project_data, owner_data = self.project_combo.currentData(), self.owner_combo.currentData()
        try:
            task_id = self.service.create_task(
                self.title_edit.text(),
                project_id=UUID(project_data) if project_data else None,
                owner_id=UUID(owner_data) if owner_data else None,
                start_date=self.start_edit.date_or_none(), due_date=self.due_edit.date_or_none(),
                priority=TaskPriority(self.priority_combo.currentData()),
            )
        except TaskValidationError as error:
            self.error_label.setText(str(error))
            return
        self.title_edit.clear()
        self.task_created.emit(task_id)
        self.accept()
