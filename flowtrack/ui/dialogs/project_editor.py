"""Create/edit dialog for project metadata."""
from __future__ import annotations
from uuid import UUID
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QLabel, QLineEdit, QPlainTextEdit, QSpinBox)
from flowtrack.application.projects import ProjectQueryService, ProjectService, ProjectValidationError
from flowtrack.domain.enums import ProgressMode, ProjectStatus
from flowtrack.ui.widgets.nullable_date_edit import NullableDateEdit

class ProjectEditorDialog(QDialog):
    project_saved = Signal(object)
    def __init__(self, service: ProjectService, queries: ProjectQueryService, parent=None) -> None:
        super().__init__(parent); self.service, self.queries = service, queries; self.project_id: UUID | None = None
        self.setMinimumWidth(480); form = QFormLayout(self)
        self.name = QLineEdit(); self.description = QPlainTextEdit(); self.description.setMaximumHeight(80)
        self.status = QComboBox(); self.colour = QLineEdit(); self.colour.setPlaceholderText("Optional colour, e.g. #7c6cf2")
        self.start = NullableDateEdit(); self.due = NullableDateEdit(); self.mode = QComboBox(); self.progress = QSpinBox(); self.progress.setRange(0,100); self.progress.setSuffix("%"); self.pin = QCheckBox("Pin in sidebar")
        for value in ProjectStatus: self.status.addItem(value.value.replace("_"," ").title(), value.value)
        for value in ProgressMode: self.mode.addItem(value.value.title(), value.value)
        self.mode.currentIndexChanged.connect(lambda: self.progress.setEnabled(self.mode.currentData()==ProgressMode.MANUAL.value))
        self.error = QLabel(); self.error.setObjectName("dangerText")
        for label, widget in (("Name",self.name),("Description",self.description),("Status",self.status),("Colour",self.colour),("Start",self.start),("Due",self.due),("Progress mode",self.mode),("Manual progress",self.progress),("",self.pin)): form.addRow(label,widget)
        form.addRow(self.error); buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); form.addRow(buttons); buttons.accepted.connect(self.submit); buttons.rejected.connect(self.reject)

    def open_for_create(self) -> None:
        self.project_id=None; self.setWindowTitle("New Project"); self.name.clear(); self.description.clear(); self.status.setCurrentIndex(0); self.colour.clear(); self.start.set_date_or_none(None); self.due.set_date_or_none(None); self.mode.setCurrentIndex(0); self.progress.setValue(0); self.pin.setChecked(False); self.error.clear(); self.open(); self.name.setFocus()

    def open_for_edit(self, project_id: UUID) -> None:
        project=self.queries.project_detail(project_id)
        if project is None:return
        self.project_id=project_id; self.setWindowTitle("Edit Project"); self.name.setText(project.name); self.description.setPlainText(project.description); self.status.setCurrentIndex(self.status.findData(project.status.value)); self.colour.setText(project.colour or ""); self.start.set_date_or_none(project.start_date); self.due.set_date_or_none(project.due_date); self.mode.setCurrentIndex(self.mode.findData(project.progress_mode.value)); self.progress.setValue(project.manual_progress); self.pin.setChecked(project.is_pinned); self.error.clear(); self.open()

    def submit(self) -> None:
        values=dict(description=self.description.toPlainText().strip() or None,status=ProjectStatus(self.status.currentData()),colour=self.colour.text().strip() or None,start_date=self.start.date_or_none(),due_date=self.due.date_or_none(),progress_mode=ProgressMode(self.mode.currentData()),manual_progress=self.progress.value(),is_pinned=self.pin.isChecked())
        try:
            if self.project_id is None:self.project_id=self.service.create_project(self.name.text(),**values)
            else:self.service.update_project(self.project_id,name=self.name.text(),**values)
        except ProjectValidationError as error:self.error.setText(str(error)); return
        self.project_saved.emit(self.project_id); self.accept()
