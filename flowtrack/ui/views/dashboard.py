"""M4 execution dashboard."""
from PySide6.QtCore import Qt, Signal
from uuid import UUID

from PySide6.QtWidgets import (
    QAbstractItemView, QGridLayout, QHeaderView, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from flowtrack.application.task_queries import TaskQueryService
from flowtrack.ui.widgets import CommandField, SectionHeading, SurfaceCard

class DashboardView(QWidget):
    TASK_ROW_MINIMUM_HEIGHT = 34

    quick_add_requested=Signal(); task_selected=Signal(object); global_search_requested=Signal()
    def __init__(self, queries:TaskQueryService,parent=None)->None:
        super().__init__(parent); self.queries=queries; layout=QVBoxLayout(self); layout.setContentsMargins(28,24,28,24); layout.setSpacing(16)
        header=QHBoxLayout(); header.addWidget(SectionHeading("Good day", "Here is what needs your attention.")); search=CommandField(); search.setPlaceholderText("Search or command…"); search.setReadOnly(True); search.mousePressEvent=lambda e:self.global_search_requested.emit(); header.addWidget(search); layout.addLayout(header)
        self.kpis={}; cards=QHBoxLayout()
        for key,label in (("active_projects","Active Projects"),("in_progress","In Progress"),("completed","Completed"),("overdue","Overdue")):
            card=SurfaceCard(); box=QVBoxLayout(card); value=QLabel("0"); value.setObjectName("pageTitle"); box.addWidget(value); box.addWidget(QLabel(label)); cards.addWidget(card); self.kpis[key]=value
        layout.addLayout(cards); content=QGridLayout(); tasks=SurfaceCard(); tb=QVBoxLayout(tasks); top=QHBoxLayout(); top.addWidget(QLabel("My Tasks · Due This Week")); add=QPushButton("+ Quick Add Task"); add.clicked.connect(self.quick_add_requested); top.addWidget(add); tb.addLayout(top)
        self.task_table = QTableWidget(0, 3)
        self.task_table.setHorizontalHeaderLabels(["Task", "Due", "Progress"])
        self.task_table.verticalHeader().hide()
        self.task_table.verticalHeader().setDefaultSectionSize(self.TASK_ROW_MINIMUM_HEIGHT)
        self.task_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.task_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.task_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.task_table.setShowGrid(False)
        header = self.task_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.task_table.cellDoubleClicked.connect(self._activate_task)
        tb.addWidget(self.task_table)
        self.empty=QLabel("Nothing due this week. Capture a task when you're ready."); self.empty.setObjectName("mutedText"); tb.addWidget(self.empty)
        projects=SurfaceCard(); pb=QVBoxLayout(projects); pb.addWidget(QLabel("Project Overview")); self.project_list=QListWidget(); pb.addWidget(self.project_list); self.pinned=QLabel(); self.pinned.setObjectName("mutedText"); pb.addWidget(self.pinned); content.addWidget(tasks,0,0); content.addWidget(projects,0,1); content.setColumnStretch(0,2); content.setColumnStretch(1,1); layout.addLayout(content,1); self.refresh()
    def refresh(self)->None:
        data=self.queries.dashboard()
        for key,label in self.kpis.items(): label.setText(str(getattr(data,key)))
        self.task_table.setRowCount(len(data.due_this_week))
        for table_row, row in enumerate(data.due_this_week):
            values = (row.title, row.due_date.strftime("%a %d %b"), f"{row.progress:.0f}%")
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, str(row.id))
                self.task_table.setItem(table_row, column, item)
        self.task_table.setVisible(bool(data.due_this_week))
        self.empty.setVisible(not data.due_this_week); self.project_list.clear()
        for _,name,progress,count,due in data.projects: self.project_list.addItem(f"{name}   {progress:.0f}%  ·  {count} tasks" + (f"  ·  {due:%d %b}" if due else ""))
        self.pinned.setText("Pinned: "+", ".join(name for _,name in data.pinned_projects) if data.pinned_projects else "No pinned projects")

    def _activate_task(self, row: int, _column: int) -> None:
        item = self.task_table.item(row, 0)
        if item is not None:
            self.task_selected.emit(UUID(item.data(Qt.ItemDataRole.UserRole)))
