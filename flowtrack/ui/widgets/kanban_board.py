"""Reusable status Kanban board for project tasks."""
from __future__ import annotations
from collections.abc import Callable
from uuid import UUID
from PySide6.QtCore import QByteArray, QEvent, QMimeData, QObject, QSize, Qt, Signal
from PySide6.QtGui import QDrag, QResizeEvent
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
MINIMUM_COLUMN_WIDTH = 190

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
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_items_to_viewport()
    def _fit_items_to_viewport(self) -> None:
        available_width=max(0,self.viewport().width()-(2*self.spacing()))
        for index in range(self.count()):
            item=self.item(index); size=item.sizeHint(); size.setWidth(available_width); item.setSizeHint(size)
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
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame); self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.columns_host=QWidget(); self.columns_layout=QHBoxLayout(self.columns_host); self.columns_layout.setContentsMargins(0,0,0,0); self.columns_layout.setSpacing(10); self.scroll.setWidget(self.columns_host); root.addWidget(self.scroll,1)
        self.scroll.viewport().installEventFilter(self)
        self.columns={}; self.column_frames={}; self.headings={}
        for status in (*WORKING_STATUSES,TaskStatus.CANCELLED):self._add_column(status)
        self.column_frames[TaskStatus.CANCELLED].hide()
        self._resize_columns()
    def _add_column(self,status:TaskStatus)->None:
        frame=QFrame(); frame.setObjectName("kanbanColumn")
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
                item=QListWidgetItem(); item.setData(Qt.ItemDataRole.UserRole,row.id); item.setSizeHint(QSize(0,92+(18 if row.parent_task_id else 0))); task_list.addItem(item); task_list.setItemWidget(item,TaskCard(row,titles.get(row.parent_task_id)))
            task_list._fit_items_to_viewport()
        self._resize_columns()
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.scroll.viewport() and event.type() is QEvent.Type.Resize:
            self._resize_columns()
        return super().eventFilter(watched,event)
    def _resize_columns(self) -> None:
        """Fit the working columns to the live viewport and overflow only for Cancelled."""
        if not hasattr(self,"column_frames") or not self.column_frames:
            return
        margins=self.columns_layout.contentsMargins(); spacing=self.columns_layout.spacing()
        available_width=(self.scroll.viewport().width()-margins.left()-margins.right()
                         - spacing*(len(WORKING_STATUSES)-1))
        column_width=max(MINIMUM_COLUMN_WIDTH,available_width//len(WORKING_STATUSES))
        remainder=max(0,available_width-column_width*len(WORKING_STATUSES))
        for index,status in enumerate(WORKING_STATUSES):
            self.column_frames[status].setFixedWidth(column_width+(1 if index < remainder else 0))
        self.column_frames[TaskStatus.CANCELLED].setFixedWidth(column_width)
        visible_count=len(WORKING_STATUSES)+(1 if self.show_cancelled.isChecked() else 0)
        visible_width=sum(self.column_frames[status].width() for status in WORKING_STATUSES)
        if self.show_cancelled.isChecked():
            visible_width+=column_width
        self.columns_host.setMinimumWidth(
            margins.left()+margins.right()+visible_width+spacing*(visible_count-1)
        )
    def move_task(self,task_id:UUID,status:TaskStatus)->bool:
        current=next((column for column in self.columns.values() if any(column.item(i).data(Qt.ItemDataRole.UserRole)==task_id for i in range(column.count()))),None)
        if current is not None and current.status is status:return False
        try:self.task_service.update_task(task_id,status=status)
        except (ValueError, RuntimeError, SQLAlchemyError) as exc:
            self.error.setText(f"Could not move task: {exc}"); self.error.show(); self.refresh(); return False
        self.error.hide(); self.refresh(); self.data_changed.emit(); return True
