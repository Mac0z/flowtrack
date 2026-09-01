"""M5 project landing and dedicated project workspace."""
from __future__ import annotations
from uuid import UUID
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget)
from flowtrack.application.projects import ProjectQueryService, ProjectService, ProjectSummary
from flowtrack.application.task_execution import TaskExecutionService
from flowtrack.domain.enums import ProjectStatus, TaskStatus
from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.ui.dialogs.project_editor import ProjectEditorDialog
from flowtrack.ui.theme import get_theme
from flowtrack.ui.theme.status import status_color
from flowtrack.ui.widgets import ProgressDisplay, SectionHeading, SurfaceCard

class ProjectsView(QWidget):
    task_selected=Signal(object); project_changed=Signal(); new_task_requested=Signal(object)
    def __init__(self, service:ProjectService, queries:ProjectQueryService, task_service:TaskExecutionService,parent=None)->None:
        super().__init__(parent); self.service,self.queries,self.task_service=service,queries,task_service; self.theme=get_theme(ApplicationSettings().theme_id); self.current_project_id:UUID|None=None; self.editor=ProjectEditorDialog(service,queries,self); self.editor.project_saved.connect(self._saved)
        root=QVBoxLayout(self); root.setContentsMargins(24,20,24,20); self.stack=QStackedWidget(); root.addWidget(self.stack)
        self.landing=QWidget(); ll=QVBoxLayout(self.landing); header=QHBoxLayout(); header.addWidget(SectionHeading("Projects","Plan and track connected work"),1); self.show_archived=QCheckBox("Show archived"); new=QPushButton("+ New Project"); new.clicked.connect(self.editor.open_for_create); header.addWidget(self.show_archived); header.addWidget(new); ll.addLayout(header)
        self.cards=QListWidget(); self.cards.setSpacing(6); self.cards.setIconSize(QSize(8,8)); self.cards.itemDoubleClicked.connect(self._open_item); ll.addWidget(self.cards,1); self.empty=QLabel("No projects yet. Create your first project to organise connected work."); self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter); self.empty.setObjectName("mutedText"); ll.addWidget(self.empty); self.show_archived.toggled.connect(self.refresh); self.stack.addWidget(self.landing)
        self.detail=QWidget(); dl=QVBoxLayout(self.detail); dh=QHBoxLayout(); back=QPushButton("‹ Projects"); back.clicked.connect(self.show_projects); self.heading=SectionHeading("Project",""); dh.addWidget(back); dh.addWidget(self.heading,1); self.pin=QPushButton(); self.pin.clicked.connect(self._toggle_pin); edit=QPushButton("Edit"); edit.clicked.connect(self._edit); self.archive=QPushButton(); self.archive.clicked.connect(self._archive); dh.addWidget(self.pin); dh.addWidget(edit); dh.addWidget(self.archive); dl.addLayout(dh)
        self.tabs=QTabWidget(); self.overview=QWidget(); self.overview_layout=QVBoxLayout(self.overview); self.metrics=QLabel(); self.metrics.setTextFormat(Qt.TextFormat.RichText); self.description=QLabel(); self.description.setWordWrap(True); self.progress=ProgressDisplay(0); self.overview_layout.addWidget(self.description); self.overview_layout.addWidget(self.progress); self.overview_layout.addWidget(self.metrics); self.overview_layout.addStretch()
        list_page=QWidget(); lp=QVBoxLayout(list_page); tools=QHBoxLayout(); tools.addWidget(QLabel("Project tasks")); tools.addStretch(); add=QPushButton("+ New Task"); add.clicked.connect(self._new_task); tools.addWidget(add); lp.addLayout(tools); self.table=QTableWidget(0,7); self.table.setHorizontalHeaderLabels(["Task","Status","Priority","Owner","Start","Due","Progress"]); self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); self.table.cellDoubleClicked.connect(self._activate_task); lp.addWidget(self.table); self.no_tasks=QLabel("No project tasks yet. Add your first task."); self.no_tasks.setAlignment(Qt.AlignmentFlag.AlignCenter); self.no_tasks.setObjectName("mutedText"); lp.addWidget(self.no_tasks)
        self.tabs.addTab(self.overview,"Overview"); self.tabs.addTab(list_page,"List"); self.tabs.addTab(self._placeholder("Board is coming in M6."),"Board"); self.tabs.addTab(self._placeholder("Gantt is coming in M7."),"Gantt"); dl.addWidget(self.tabs); self.stack.addWidget(self.detail); self.refresh()

    @staticmethod
    def _placeholder(text:str)->QWidget:
        page=QWidget(); layout=QVBoxLayout(page); label=QLabel(text); label.setObjectName("mutedText"); label.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(label); return page
    def refresh(self,*_)->None:
        projects=self.queries.list_projects(include_archived=self.show_archived.isChecked()); self.cards.clear()
        for project in projects:
            item=QListWidgetItem(("📌  " if project.is_pinned else "")+f"{project.name}\n{project.status.value.replace('_',' ').title()}   ·   {project.progress:.0f}%   ·   {project.task_count} tasks"+(f"   ·   Due {project.due_date.isoformat()}" if project.due_date else "")); item.setData(Qt.ItemDataRole.UserRole,project.id); item.setToolTip(project.description); item.setSizeHint(item.sizeHint().expandedTo(QSize(0,62)))
            project_colour=QColor(project.colour)
            if project_colour.isValid():
                marker=QPixmap(8,8); marker.fill(project_colour); item.setIcon(QIcon(marker))
            if project.status is ProjectStatus.ARCHIVED:item.setForeground(QColor(self.theme.colors.text_muted))
            self.cards.addItem(item)
        self.empty.setVisible(not projects); self.cards.setVisible(bool(projects))
        if self.current_project_id and self.stack.currentWidget() is self.detail:self._load_detail()
    def open_project(self,project_id:UUID)->None:self.current_project_id=project_id; self._load_detail(); self.stack.setCurrentWidget(self.detail)
    def show_projects(self)->None:self.current_project_id=None; self.stack.setCurrentWidget(self.landing); self.refresh()
    def _open_item(self,item:QListWidgetItem)->None:self.open_project(item.data(Qt.ItemDataRole.UserRole))
    def _load_detail(self)->None:
        if self.current_project_id is None:return
        p=self.queries.project_detail(self.current_project_id)
        if p is None:self.show_projects();return
        self.heading.title.setText(p.name); self.heading.subtitle.setText(p.status.value.replace('_',' ').title()+f" · {p.progress:.0f}% complete"); self.heading.subtitle.show(); self.pin.setText("Unpin" if p.is_pinned else "Pin"); self.archive.setText("Unarchive" if p.status is ProjectStatus.ARCHIVED else "Archive"); self.description.setText(p.description or "No description"); self.progress.set_percentage(p.progress); self.metrics.setText(f"<b>Status:</b> {p.status.value.replace('_',' ').title()} &nbsp; <b>Progress mode:</b> {p.progress_mode.value.title()}<br><b>Start:</b> {p.start_date or '—'} &nbsp; <b>Due:</b> {p.due_date or '—'}<br><b>Tasks:</b> {p.task_count} &nbsp; <b>Completed:</b> {p.completed_count} &nbsp; <b>Overdue:</b> {p.overdue_count} &nbsp; <b>Blocked:</b> {p.blocked_count}")
        rows=self.queries.project_tasks(p.id); self.table.setRowCount(len(rows)); self.no_tasks.setVisible(not rows); self.table.setVisible(bool(rows))
        for r,row in enumerate(rows):
            values=(('    '*row.hierarchy_depth)+row.title,row.status.value.replace('_',' ').title(),row.priority.value.title(),row.owner_name or '—',row.start_date.isoformat() if row.start_date else '—',row.due_date.isoformat() if row.due_date else '—')
            for c,value in enumerate(values):
                item=QTableWidgetItem(value); item.setData(Qt.ItemDataRole.UserRole,row.id); item.setData(Qt.ItemDataRole.UserRole+1,row.hierarchy_depth)
                if c==1:item.setForeground(QColor(status_color(self.theme,row.status)))
                elif row.status in (TaskStatus.COMPLETE,TaskStatus.CANCELLED):item.setForeground(QColor(self.theme.colors.text_muted))
                self.table.setItem(r,c,item)
            self.table.setCellWidget(r,6,ProgressDisplay(row.progress))
        self.table.resizeColumnsToContents()
    def _activate_task(self,row:int,_column:int)->None:self.task_selected.emit(self.table.item(row,0).data(Qt.ItemDataRole.UserRole))
    def _new_task(self)->None:
        if self.current_project_id:self.new_task_requested.emit(self.current_project_id)
    def _toggle_pin(self)->None:
        p=self.queries.project_detail(self.current_project_id) if self.current_project_id else None
        if p:self.service.set_pinned(p.id,not p.is_pinned); self.refresh(); self.project_changed.emit()
    def _archive(self)->None:
        p=self.queries.project_detail(self.current_project_id) if self.current_project_id else None
        if not p:return
        if p.status is ProjectStatus.ARCHIVED:self.service.unarchive_project(p.id)
        else:self.service.archive_project(p.id)
        self.refresh(); self.project_changed.emit()
    def _edit(self)->None:
        if self.current_project_id:self.editor.open_for_edit(self.current_project_id)
    def _saved(self,project_id:object)->None:self.current_project_id=project_id; self.refresh(); self.project_changed.emit(); self.open_project(project_id)
