"""Right-hand task inspector for detailed M4 edits."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
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


class DependencyRow(QWidget):
    """Readable dependency entry with an unambiguous remove action."""

    remove_requested = Signal(object)

    def __init__(self, task_id: UUID, title: str, context: str,
                 *, removable: bool, parent=None) -> None:
        super().__init__(parent)
        self.task_id = task_id
        self.setObjectName("dependencyRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 2, 3)
        layout.setSpacing(4)
        text = QLabel(f"{title}\n{context}")
        text.setObjectName("dependencyText")
        layout.addWidget(text, 1)
        if removable:
            remove = QPushButton("×")
            remove.setObjectName("dependencyRemove")
            remove.setAccessibleName(f"Remove dependency on {title}")
            remove.setToolTip(f"Remove dependency on {title}")
            remove.clicked.connect(lambda: self.remove_requested.emit(self.task_id))
            layout.addWidget(remove)


class TaskInspector(QWidget):
    closed = Signal()
    saved = Signal()
    deleted = Signal()

    def __init__(self, service: TaskExecutionService, queries: TaskQueryService,
                 parent=None, *, read_only: bool = False) -> None:
        super().__init__(parent)
        self.service, self.queries, self.read_only = service, queries, read_only
        self.task_id: UUID | None = None
        self.setFixedWidth(390)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("TASK INSPECTOR"))
        close = QPushButton("×")
        close.setAccessibleName("Close task inspector")
        close.setToolTip("Close task inspector (Esc)")
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
        self.children = QLabel()
        self.dependency_editor = QWidget()
        dependency_layout = QVBoxLayout(self.dependency_editor)
        dependency_layout.setContentsMargins(0, 0, 0, 0)
        dependency_layout.setSpacing(5)
        depends_heading = QLabel("DEPENDS ON")
        depends_heading.setObjectName("mutedText")
        dependency_layout.addWidget(depends_heading)
        add_dependency_layout = QHBoxLayout()
        self.dependency_picker = QComboBox()
        self.dependency_picker.setEditable(True)
        self.dependency_picker.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.dependency_picker.setPlaceholderText("Select or search tasks…")
        self.dependency_picker.setAccessibleName("Dependency task picker")
        completer = self.dependency_picker.completer()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.add_dependency_button = QPushButton("Add")
        self.add_dependency_button.clicked.connect(self.add_selected_dependency)
        add_dependency_layout.addWidget(self.dependency_picker, 1)
        add_dependency_layout.addWidget(self.add_dependency_button)
        dependency_layout.addLayout(add_dependency_layout)
        self.predecessors_widget = QWidget()
        self.predecessors_layout = QVBoxLayout(self.predecessors_widget)
        self.predecessors_layout.setContentsMargins(0, 0, 0, 0)
        self.predecessors_layout.setSpacing(3)
        dependency_layout.addWidget(self.predecessors_widget)
        self.no_predecessors = QLabel("No dependencies")
        self.no_predecessors.setObjectName("mutedText")
        dependency_layout.addWidget(self.no_predecessors)
        blocks_heading = QLabel("BLOCKS")
        blocks_heading.setObjectName("mutedText")
        dependency_layout.addWidget(blocks_heading)
        self.successors_widget = QWidget()
        self.successors_layout = QVBoxLayout(self.successors_widget)
        self.successors_layout.setContentsMargins(0, 0, 0, 0)
        self.successors_layout.setSpacing(3)
        dependency_layout.addWidget(self.successors_widget)
        self.no_successors = QLabel("Nothing currently depends on this task")
        self.no_successors.setObjectName("mutedText")
        dependency_layout.addWidget(self.no_successors)
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
                              ("Children", self.children), ("Dependencies", self.dependency_editor)):
            form.addRow(label, widget)
        layout.addLayout(form)
        self.error = QLabel()
        self.error.setObjectName("dangerText")
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        save, child, delete_button = QPushButton("Save"), QPushButton("Add child"), QPushButton("Delete…")
        self.save_button, self.add_child_button, self.delete_button = save, child, delete_button
        save.clicked.connect(self.save)
        child.clicked.connect(self.add_child)
        delete_button.clicked.connect(self.request_delete)
        for button in (save, child, delete_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        layout.addStretch()
        if read_only:
            for widget in (self.title, self.description, self.status, self.priority, self.owner,
                           self.start, self.due, self.progress_mode, self.progress,
                           self.tag_editor, self.dependency_editor, save, child, delete_button):
                widget.setEnabled(False)
            self.setToolTip("Task details are view-only because this dataset is read-only.")
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
        self._refresh_dependencies()
        self.show()

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _refresh_dependencies(self) -> None:
        if self.task_id is None:
            return
        data = self.queries.task_dependencies(self.task_id)
        self._clear_layout(self.predecessors_layout)
        self._clear_layout(self.successors_layout)
        for task in data.predecessors:
            row = DependencyRow(task.task_id, task.title, self._dependency_context(task),
                                removable=not self.read_only, parent=self.predecessors_widget)
            row.remove_requested.connect(self.remove_predecessor)
            self.predecessors_layout.addWidget(row)
        for task in data.successors:
            row = DependencyRow(task.task_id, task.title, self._dependency_context(task),
                                removable=False, parent=self.successors_widget)
            self.successors_layout.addWidget(row)
        self.no_predecessors.setVisible(not data.predecessors)
        self.no_successors.setVisible(not data.successors)
        self.dependency_picker.clear()
        self.dependency_picker.addItem("Select or search tasks…", None)
        for task in data.add_choices:
            self.dependency_picker.addItem(
                f"{task.title} — {task.project_name or 'No project'} · "
                f"{task.status.value.replace('_', ' ').title()}", str(task.task_id))
        enabled = bool(data.add_choices) and not self.read_only
        self.dependency_picker.setEnabled(enabled)
        self.add_dependency_button.setEnabled(enabled)

    @staticmethod
    def _dependency_context(task) -> str:
        return (f"{task.project_name or 'No project'} · "
                f"{task.status.value.replace('_', ' ').title()}")

    def add_selected_dependency(self) -> None:
        if self.task_id is None or self.dependency_picker.currentData() is None:
            return
        try:
            self.service.add_dependency(UUID(self.dependency_picker.currentData()), self.task_id)
        except (TaskValidationError, ValueError) as error:
            self.error.setText(str(error))
            return
        self.error.clear()
        self._refresh_dependencies()
        self.saved.emit()

    def remove_predecessor(self, predecessor_id: object) -> None:
        if self.task_id is None or self.read_only:
            return
        task = next((item for item in self.queries.task_dependencies(self.task_id).predecessors
                     if item.task_id == UUID(str(predecessor_id))), None)
        title = task.title if task else "this task"
        if not self.confirm_dependency_removal(title):
            return
        self.service.remove_dependency(UUID(str(predecessor_id)), self.task_id)
        self.error.clear()
        self._refresh_dependencies()
        self.saved.emit()

    def confirm_dependency_removal(self, title: str) -> bool:
        """Ask for an explicit, safely-defaulted destructive decision."""
        dialog = QMessageBox(QMessageBox.Icon.Warning, "Remove Dependency",
                             f"Remove the dependency on '{title}'? Scheduling will no longer enforce this relationship.",
                             parent=self)
        remove_button = dialog.addButton("Remove Dependency", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(cancel_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec()
        return dialog.clickedButton() is remove_button

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
