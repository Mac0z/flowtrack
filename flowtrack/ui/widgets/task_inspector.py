"""Right-hand task inspector for detailed M4 edits."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from flowtrack.application.task_execution import TaskExecutionService, TaskValidationError
from flowtrack.application.task_queries import TaskQueryService
from flowtrack.domain.enums import ProgressMode, TaskPriority, TaskStatus
from flowtrack.ui.widgets.nullable_date_edit import NullableDateEdit


class TagChip(QWidget):
    """Compact assigned-tag row with an explicit remove action."""

    remove_requested = Signal(str)

    def __init__(self, tag_id: str, name: str, parent=None) -> None:
        super().__init__(parent)
        self.tag_id = tag_id
        self.setObjectName("tagChip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 2, 2)
        layout.setSpacing(4)
        layout.addWidget(QLabel(name), 1)
        remove = QPushButton("×")
        remove.setObjectName("tagChipRemove")
        remove.setAccessibleName(f"Remove {name}")
        remove.clicked.connect(lambda: self.remove_requested.emit(self.tag_id))
        layout.addWidget(remove)


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
        self.progress_mode = QComboBox()
        self.progress = QSpinBox()
        self.progress.setRange(0, 100)
        self.progress.setSuffix("%")
        self._automatic_progress = 0
        self._manual_progress = 0
        self._loaded_progress_mode = ProgressMode.AUTOMATIC
        self.assigned_tag_ids: set[str] = set()
        self._all_tags: dict[str, str] = {}
        self.tag_editor = QWidget()
        tag_layout = QVBoxLayout(self.tag_editor)
        tag_layout.setContentsMargins(0, 0, 0, 0)
        add_tag_layout = QHBoxLayout()
        self.available_tags = QComboBox()
        self.available_tags.setAccessibleName("Available tags")
        self.add_tag_button = QPushButton("Add")
        self.add_tag_button.clicked.connect(self.add_selected_tag)
        add_tag_layout.addWidget(self.available_tags, 1)
        add_tag_layout.addWidget(self.add_tag_button)
        tag_layout.addLayout(add_tag_layout)
        self.assigned_tags = QWidget()
        self.assigned_tags_layout = QVBoxLayout(self.assigned_tags)
        self.assigned_tags_layout.setContentsMargins(0, 0, 0, 0)
        self.assigned_tags_layout.setSpacing(4)
        tag_layout.addWidget(self.assigned_tags)
        self.no_tags = QLabel("No tags")
        self.no_tags.setObjectName("mutedText")
        tag_layout.addWidget(self.no_tags)
        self.children, self.dependencies = QLabel(), QLabel()
        for value in TaskStatus:
            self.status.addItem(value.value.replace("_", " ").title(), value.value)
        for value in TaskPriority:
            self.priority.addItem(value.value.title(), value.value)
        for value in ProgressMode:
            self.progress_mode.addItem(value.value.title(), value.value)
        self.progress_mode.currentIndexChanged.connect(self._progress_mode_changed)
        for label, widget in (("Title", self.title), ("Description", self.description),
                              ("Status", self.status), ("Priority", self.priority),
                              ("Owner", self.owner), ("Start", self.start), ("Due", self.due),
                              ("Progress mode", self.progress_mode), ("Progress", self.progress), ("Tags", self.tag_editor),
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
        self._automatic_progress = round(float(detail["automatic_progress"]))
        self._manual_progress = int(detail["manual_progress"])
        self._loaded_progress_mode = ProgressMode(detail["progress_mode"])
        self._select_data(self.progress_mode, detail["progress_mode"])
        self.progress.setValue(round(float(detail["progress"])))
        self.progress.setReadOnly(self._loaded_progress_mode is ProgressMode.AUTOMATIC)
        self._all_tags = {str(tag_id): name for tag_id, name in self.queries.tags()}
        self.assigned_tag_ids = {str(tag_id) for tag_id, _ in detail["tags"]}  # type: ignore[union-attr]
        self._refresh_tags()
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
                status=TaskStatus(self.status.currentData()),
                priority=TaskPriority(self.priority.currentData()),
                owner_id=UUID(owner_data) if owner_data else None,
                start_date=self.start.date_or_none(), due_date=self.due.date_or_none(),
                progress_mode=ProgressMode(self.progress_mode.currentData()),
                manual_progress=(self.progress.value()
                                 if ProgressMode(self.progress_mode.currentData()) is ProgressMode.MANUAL
                                 else self._manual_progress),
            )
            self.service.set_tags(
                self.task_id,
                [UUID(tag_id) for tag_id in sorted(self.assigned_tag_ids)],
            )
        except TaskValidationError as error:
            self.error.setText(str(error))
            return
        self.error.clear()
        self.saved.emit()
        self.load_task(self.task_id)

    def _progress_mode_changed(self) -> None:
        data = self.progress_mode.currentData()
        if data is None:
            return
        mode = ProgressMode(data)
        if mode is ProgressMode.AUTOMATIC:
            self.progress.setValue(self._automatic_progress)
            self.progress.setReadOnly(True)
        else:
            if self._loaded_progress_mode is ProgressMode.MANUAL:
                value = self._manual_progress
            else:
                value = self._manual_progress or self._automatic_progress
            self.progress.setValue(value)
            self.progress.setReadOnly(False)

    def add_child(self) -> None:
        if self.task_id is None:
            return
        try:
            today = date.today()
            child = self.service.create_task(
                "New child task", parent_task_id=self.task_id,
                start_date=today, due_date=today + timedelta(days=1),
            )
        except TaskValidationError as error:
            self.error.setText(str(error))
            return
        self.saved.emit()
        self.load_task(child)

    def add_selected_tag(self) -> None:
        tag_id = self.available_tags.currentData()
        if tag_id is not None:
            self.assigned_tag_ids.add(str(tag_id))
            self._refresh_tags()

    def remove_tag(self, tag_id: str) -> None:
        self.assigned_tag_ids.discard(tag_id)
        self._refresh_tags()

    def _refresh_tags(self) -> None:
        while self.assigned_tags_layout.count():
            item = self.assigned_tags_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for tag_id in sorted(self.assigned_tag_ids, key=lambda value: self._all_tags.get(value, "").casefold()):
            chip = TagChip(tag_id, self._all_tags.get(tag_id, tag_id), self.assigned_tags)
            chip.remove_requested.connect(self.remove_tag)
            self.assigned_tags_layout.addWidget(chip)
        self.available_tags.clear()
        for tag_id, name in sorted(self._all_tags.items(), key=lambda item: item[1].casefold()):
            if tag_id not in self.assigned_tag_ids:
                self.available_tags.addItem(name, tag_id)
        self.available_tags.setEnabled(self.available_tags.count() > 0)
        self.add_tag_button.setEnabled(self.available_tags.count() > 0)
        self.no_tags.setVisible(not self.assigned_tag_ids)

    def request_delete(self) -> None:
        self.deleted.emit()

    def close_inspector(self) -> None:
        self.hide()
        self.closed.emit()
