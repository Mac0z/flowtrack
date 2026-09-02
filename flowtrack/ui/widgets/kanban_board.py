"""Reusable status Kanban board for project tasks."""
from __future__ import annotations
from collections.abc import Callable
from uuid import UUID
from PySide6.QtCore import QByteArray, QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QDrag
from sqlalchemy.exc import SQLAlchemyError
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QScrollArea, QVBoxLayout, QWidget)
from flowtrack.application.projects import ProjectQueryService
from flowtrack.application.task_execution import TaskExecutionService
from flowtrack.application.task_queries import TaskRow
from flowtrack.domain.enums import TaskStatus
from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.ui.theme import get_theme
from flowtrack.ui.theme.status import status_color

TASK_MIME_TYPE = "application/x-flowtrack-task-id"
WORKING_STATUSES = (TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED,
                    TaskStatus.WAITING, TaskStatus.COMPLETE)

def _status_label(status: TaskStatus) -> str:
    return status.value.replace("_", " ").title()

class KanbanColumnList(QListWidget):
    """A list that only accepts task-status moves, never item reordering."""
    def __init__(self, status: TaskStatus, move_task: Callable[[UUID, TaskStatus], bool], parent=None) -> None:
        super().__init__(parent); self.status=status; self._move_task=move_task
        self.setObjectName("kanbanColumnList"); self.setDragEnabled(True); self.setAcceptDrops(True)
        self.setDropIndicatorShown(True); self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection); self.setSpacing(7)
    def startDrag(self, _supported_actions: Qt.DropAction) -> None:
        item=self.currentItem()
        if item is None:return
        mime=QMimeData(); mime.setData(TASK_MIME_TYPE,QByteArray(str(item.data(Qt.ItemDataRole.UserRole)).encode("ascii")))
        drag=QDrag(self); drag.setMimeData(mime); rect=self.visualItemRect(item)
        drag.setPixmap(self.viewport().grab(rect)); drag.setHotSpot(rect.center()); drag.exec(Qt.DropAction.MoveAction)
    def dragEnterEvent(self,event) -> None:
        event.acceptProposedAction() if event.mimeData().hasFormat(TASK_MIME_TYPE) else event.ignore()
    def dragMoveEvent(self,event) -> None:
        event.acceptProposedAction() if event.mimeData().hasFormat(TASK_MIME_TYPE) else event.ignore()
    def dropEvent(self,event) -> None:
        if not event.mimeData().hasFormat(TASK_MIME_TYPE):event.ignore();return
        try: task_id=UUID(bytes(event.mimeData().data(TASK_MIME_TYPE)).decode("ascii"))
        except (ValueError,UnicodeDecodeError):event.ignore();return
        if self._move_task(task_id,self.status):event.setDropAction(Qt.DropAction.MoveAction);event.accept()
        else:event.ignore()

class TaskCard(QFrame):
    """Compact presentation of a task read model; it contains no business logic."""
    def __init__(self,task:TaskRow,parent_title:str|None,parent=None)->None:
        super().__init__(parent); theme=get_theme(ApplicationSettings().theme_id); self.setObjectName("kanbanCard")
        self.setAccessibleName(f"Task: {task.title}"); layout=QVBoxLayout(self); layout.setContentsMargins(11,9,11,9); layout.setSpacing(5)
        if parent_title:
            context=QLabel(f"↳ {parent_title}"); context.setObjectName("mutedText"); context.setToolTip(f"Child of {parent_title}"); layout.addWidget(context)
        title=QLabel(task.title); title.setWordWrap(True); title.setStyleSheet(f"font-weight: {theme.typography.weight_semibold};"); layout.addWidget(title)
        details=[]
        if task.owner_name:details.append(task.owner_name)
        details.append(task.priority.value.title())
        if task.due_date:details.append(("Overdue " if task.overdue else "Due ")+task.due_date.isoformat())
        metadata=QLabel("  ·  ".join(details)); metadata.setWordWrap(True)
        metadata.setStyleSheet(f"color: {theme.colors.danger if task.overdue else theme.colors.text_secondary};"); layout.addWidget(metadata)
        progress=QLabel(f"{task.progress:.0f}% complete"); progress.setObjectName("mutedText"); layout.addWidget(progress)
        foreground=theme.colors.text_muted if task.status is TaskStatus.COMPLETE else theme.colors.text_primary
        self.setStyleSheet(f"QFrame#kanbanCard {{ background: {theme.colors.surface_secondary}; border: 1px solid {theme.colors.border_subtle}; border-left: 3px solid {status_color(theme,task.status)}; border-radius: {theme.radii.md}px; color: {foreground}; }}")

class ProjectBoard(QWidget):
    """Status board backed by the project's existing query and command services."""
    task_activated=Signal(object); data_changed=Signal()
    def __init__(self,task_service:TaskExecutionService,queries:ProjectQueryService,parent=None)->None:
        super().__init__(parent); self.task_service=task_service; self.queries=queries; self.project_id:UUID|None=None
        self.theme=get_theme(ApplicationSettings().theme_id); root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0)
        tools=QHBoxLayout(); label=QLabel("Project board"); label.setStyleSheet(f"font-weight: {self.theme.typography.weight_semibold};")
        tools.addWidget(label); tools.addStretch(); self.show_cancelled=QCheckBox("Show Cancelled"); self.show_cancelled.toggled.connect(self.refresh); tools.addWidget(self.show_cancelled); root.addLayout(tools)
        self.error=QLabel(); self.error.setObjectName("dangerText"); self.error.setWordWrap(True); self.error.hide(); root.addWidget(self.error)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.columns_host=QWidget(); self.columns_layout=QHBoxLayout(self.columns_host); self.columns_layout.setContentsMargins(0,0,0,0); self.columns_layout.setSpacing(10); scroll.setWidget(self.columns_host); root.addWidget(scroll,1)
        self.columns={}; self.column_frames={}; self.headings={}
        for status in (*WORKING_STATUSES,TaskStatus.CANCELLED):self._add_column(status)
        self.column_frames[TaskStatus.CANCELLED].hide()
    def _add_column(self,status:TaskStatus)->None:
        frame=QFrame(); frame.setObjectName("kanbanColumn"); frame.setMinimumWidth(224); frame.setMaximumWidth(310)
        frame.setStyleSheet(f"QFrame#kanbanColumn {{ background: {self.theme.colors.surface_primary}; border: 1px solid {self.theme.colors.border_subtle}; border-radius: {self.theme.radii.lg}px; }}")
        layout=QVBoxLayout(frame); layout.setContentsMargins(9,10,9,9); heading=QLabel(); heading.setStyleSheet(f"color: {status_color(self.theme,status)}; font-weight: {self.theme.typography.weight_semibold};"); layout.addWidget(heading)
        task_list=KanbanColumnList(status,self.move_task); task_list.itemClicked.connect(lambda item:self.task_activated.emit(item.data(Qt.ItemDataRole.UserRole))); task_list.itemDoubleClicked.connect(lambda item:self.task_activated.emit(item.data(Qt.ItemDataRole.UserRole))); layout.addWidget(task_list,1); self.columns_layout.addWidget(frame)
        self.columns[status],self.column_frames[status],self.headings[status]=task_list,frame,heading
    def set_project(self,project_id:UUID|None)->None:self.project_id=project_id;self.refresh()
    def refresh(self,*_args)->None:
        rows=self.queries.project_tasks(self.project_id) if self.project_id else []; titles={row.id:row.title for row in rows}; grouped={status:[] for status in self.columns}
        for row in rows:grouped[row.status].append(row)
        self.column_frames[TaskStatus.CANCELLED].setVisible(self.show_cancelled.isChecked())
        for status,task_list in self.columns.items():
            task_list.clear(); visible_rows=grouped[status]; self.headings[status].setText(f"{_status_label(status)}   {len(visible_rows)}")
            for row in visible_rows:
                item=QListWidgetItem(); item.setData(Qt.ItemDataRole.UserRole,row.id); item.setSizeHint(QSize(200,92+(18 if row.parent_task_id else 0))); task_list.addItem(item); task_list.setItemWidget(item,TaskCard(row,titles.get(row.parent_task_id)))
    def move_task(self,task_id:UUID,status:TaskStatus)->bool:
        current=next((column for column in self.columns.values() if any(column.item(i).data(Qt.ItemDataRole.UserRole)==task_id for i in range(column.count()))),None)
        if current is not None and current.status is status:return False
        try:self.task_service.update_task(task_id,status=status)
        except (ValueError, RuntimeError, SQLAlchemyError) as exc:
            self.error.setText(f"Could not move task: {exc}"); self.error.show(); self.refresh(); return False
        self.error.hide(); self.refresh(); self.data_changed.emit(); return True
