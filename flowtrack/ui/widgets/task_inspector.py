"""Right-hand task inspector for detailed M4 edits."""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from flowtrack.application.task_execution import TaskExecutionService, TaskValidationError
from flowtrack.application.task_queries import TaskQueryService
from flowtrack.domain.enums import TaskPriority, TaskStatus
from flowtrack.ui.widgets.nullable_date_edit import NullableDateEdit


class TaskInspector(QWidget):
    closed = Signal()
    saved = Signal()
    deleted = Signal()

    def __init__(self, service: TaskExecutionService, queries: TaskQueryService, parent=None) -> None:
        super().__init__(parent)
        self.service, self.queries = service, queries
        self.task_id: UUID | None = None
        self.setFixedWidth(390)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("TASK INSPECTOR"))
        close = QPushButton("×")
        close.clicked.connect(self.close_inspector)
        top.addWidget(close)
        layout.addLayout(top)
        form = QFormLayout()
        self.title = QLineEdit()
        self.description = QPlainTextEdit()
        self.description.setMaximumHeight(90)
        self.status = QComboBox()
        self.priority = QComboBox()
        self.owner = QComboBox()
        self.start = NullableDateEdit()
        self.due = NullableDateEdit()
        self.progress = QProgressBar()
        self.tags = QListWidget()
        self.tags.setMaximumHeight(80)
        self.tags.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.children, self.dependencies = QLabel(), QLabel()
        for value in TaskStatus:
            self.status.addItem(value.value.replace("_", " ").title(), value)
        for value in TaskPriority:
            self.priority.addItem(value.value.title(), value)
        for label, widget in (("Title", self.title), ("Description", self.description),
                              ("Status", self.status), ("Priority", self.priority),
                              ("Owner", self.owner), ("Start", self.start), ("Due", self.due),
                              ("Progress", self.progress), ("Tags", self.tags),
                              ("Children", self.children), ("Dependencies", self.dependencies)):
            form.addRow(label, widget)
        layout.addLayout(form)
        self.error = QLabel()
        self.error.setObjectName("dangerText")
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        save, child, delete_button = QPushButton("Save"), QPushButton("Add child"), QPushButton("Delete…")
        save.clicked.connect(self.save)
        child.clicked.connect(self.add_child)
        delete_button.clicked.connect(self.request_delete)
        for button in (save, child, delete_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        layout.addStretch()
        self.hide()

    @staticmethod
    def _stable_id(value: object) -> str | None:
        return None if value is None else str(value)

    def _select_data(self, combo: QComboBox, value: object) -> None:
        wanted = self._stable_id(value)
        index = next((i for i in range(combo.count())
                      if self._stable_id(combo.itemData(i)) == wanted), -1)
        combo.setCurrentIndex(index)

    def load_task(self, task_id: UUID) -> None:
        detail = self.queries.task_detail(task_id)
        if detail is None:
            return
        self.task_id = task_id
        self.title.setText(str(detail["title"]))
        self.description.setPlainText(str(detail["description"]))
        self._select_data(self.status, detail["status"])
        self._select_data(self.priority, detail["priority"])
        self.owner.clear()
        self.owner.addItem("Unassigned", None)
        current_owner = self._stable_id(detail["owner_id"])
        for owner_id, name, active in self.queries.owners():
            if active or self._stable_id(owner_id) == current_owner:
                label = name if active else f"{name} (inactive)"
                self.owner.addItem(label, str(owner_id))
        self._select_data(self.owner, detail["owner_id"])
        self.start.set_date_or_none(detail["start_date"])  # type: ignore[arg-type]
        self.due.set_date_or_none(detail["due_date"])  # type: ignore[arg-type]
        self.progress.setValue(round(float(detail["progress"])))
        self.tags.clear()
        selected = {self._stable_id(tag_id) for tag_id, _ in detail["tags"]}  # type: ignore[union-attr]
        for tag_id, name in self.queries.tags():
            self.tags.addItem(name)
            item = self.tags.item(self.tags.count() - 1)
            item.setData(Qt.ItemDataRole.UserRole, str(tag_id))
            item.setSelected(str(tag_id) in selected)
        self.children.setText("\n".join(name for _, name, _ in detail["children"]) or "None")  # type: ignore[union-attr]
        self.dependencies.setText("\n".join(name for _, name in detail["dependencies"]) or "None")  # type: ignore[union-attr]
        self.show()

    def save(self) -> None:
        if self.task_id is None:
            return
        try:
            owner_data = self.owner.currentData()
            self.service.update_task(
                self.task_id, title=self.title.text(), description=self.description.toPlainText(),
                status=self.status.currentData(), priority=self.priority.currentData(),
                owner_id=UUID(owner_data) if owner_data else None,
                start_date=self.start.date_or_none(), due_date=self.due.date_or_none(),
            )
            self.service.set_tags(
                self.task_id,
                [UUID(item.data(Qt.ItemDataRole.UserRole)) for item in self.tags.selectedItems()],
            )
        except TaskValidationError as error:
            self.error.setText(str(error))
            return
        self.error.clear()
        self.saved.emit()
        self.load_task(self.task_id)

    def add_child(self) -> None:
        if self.task_id is None:
            return
        try:
            child = self.service.create_task("New child task", parent_task_id=self.task_id)
        except TaskValidationError as error:
            self.error.setText(str(error))
            return
        self.saved.emit()
        self.load_task(child)

    def request_delete(self) -> None:
        self.deleted.emit()

    def close_inspector(self) -> None:
        self.hide()
        self.closed.emit()
