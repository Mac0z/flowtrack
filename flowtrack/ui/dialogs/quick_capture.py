"""Compact M4 quick task capture dialog."""
from datetime import date
from uuid import UUID
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit
from flowtrack.application.task_execution import TaskExecutionService, TaskValidationError
from flowtrack.application.task_queries import TaskQueryService
from flowtrack.domain.enums import TaskPriority

class QuickCaptureDialog(QDialog):
    task_created = Signal(object)
    def __init__(self, service: TaskExecutionService, queries: TaskQueryService, parent=None) -> None:
        super().__init__(parent); self.service, self.queries = service, queries
        self.setWindowTitle("Quick Add Task"); self.setMinimumWidth(430)
        form = QFormLayout(self); self.title_edit = QLineEdit(); self.title_edit.setPlaceholderText("What needs doing?")
        self.project_combo = QComboBox(); self.owner_combo = QComboBox(); self.priority_combo = QComboBox()
        self.project_combo.addItem("No project", None); self.owner_combo.addItem("Unassigned", None)
        for value in TaskPriority: self.priority_combo.addItem(value.value.replace("_", " ").title(), value)
        self.priority_combo.setCurrentIndex(list(TaskPriority).index(TaskPriority.MEDIUM))
        self.due_edit = QDateEdit(); self.due_edit.setCalendarPopup(True); self.due_edit.setSpecialValueText("No due date"); self.due_edit.setMinimumDate(date(1900,1,1)); self.due_edit.setDate(self.due_edit.minimumDate())
        self.error_label = QLabel(); self.error_label.setObjectName("dangerText")
        for label, widget in (("Title",self.title_edit),("Project",self.project_combo),("Owner",self.owner_combo),("Due",self.due_edit),("Priority",self.priority_combo)): form.addRow(label, widget)
        form.addRow(self.error_label); buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); form.addRow(buttons)
        buttons.accepted.connect(self.submit); buttons.rejected.connect(self.reject); self.title_edit.returnPressed.connect(self.submit); self.refresh_options()
    def refresh_options(self) -> None:
        while self.project_combo.count()>1: self.project_combo.removeItem(1)
        while self.owner_combo.count()>1: self.owner_combo.removeItem(1)
        for id_, name in self.queries.projects(): self.project_combo.addItem(name,id_)
        for id_, name, _ in self.queries.owners(True): self.owner_combo.addItem(name,id_)
    def open(self) -> None:
        self.refresh_options(); self.error_label.clear(); super().open(); self.title_edit.setFocus()
    def submit(self) -> None:
        due = None if self.due_edit.date()==self.due_edit.minimumDate() else self.due_edit.date().toPython()
        try: task_id=self.service.create_task(self.title_edit.text(), project_id=self.project_combo.currentData(), owner_id=self.owner_combo.currentData(), due_date=due, priority=self.priority_combo.currentData())
        except TaskValidationError as error: self.error_label.setText(str(error)); return
        self.title_edit.clear(); self.task_created.emit(task_id); self.accept()
