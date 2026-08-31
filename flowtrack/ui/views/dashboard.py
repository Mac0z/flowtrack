"""M4 execution dashboard."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget
from flowtrack.application.task_queries import TaskQueryService
from flowtrack.ui.widgets import CommandField, ProgressDisplay, SectionHeading, SurfaceCard

class DashboardView(QWidget):
    quick_add_requested=Signal(); task_selected=Signal(object); global_search_requested=Signal()
    def __init__(self, queries:TaskQueryService,parent=None)->None:
        super().__init__(parent); self.queries=queries; layout=QVBoxLayout(self); layout.setContentsMargins(28,24,28,24); layout.setSpacing(16)
        header=QHBoxLayout(); header.addWidget(SectionHeading("Good day", "Here is what needs your attention.")); search=CommandField(); search.setPlaceholderText("Search or command…"); search.setReadOnly(True); search.mousePressEvent=lambda e:self.global_search_requested.emit(); header.addWidget(search); layout.addLayout(header)
        self.kpis={}; cards=QHBoxLayout()
        for key,label in (("active_projects","Active Projects"),("in_progress","In Progress"),("completed","Completed"),("overdue","Overdue")):
            card=SurfaceCard(); box=QVBoxLayout(card); value=QLabel("0"); value.setObjectName("pageTitle"); box.addWidget(value); box.addWidget(QLabel(label)); cards.addWidget(card); self.kpis[key]=value
        layout.addLayout(cards); content=QGridLayout(); tasks=SurfaceCard(); tb=QVBoxLayout(tasks); top=QHBoxLayout(); top.addWidget(QLabel("My Tasks · Due This Week")); add=QPushButton("+ Quick Add Task"); add.clicked.connect(self.quick_add_requested); top.addWidget(add); tb.addLayout(top); self.task_list=QListWidget(); self.task_list.itemActivated.connect(lambda item:self.task_selected.emit(item.data(256))); tb.addWidget(self.task_list); self.empty=QLabel("Nothing due this week. Capture a task when you're ready."); self.empty.setObjectName("mutedText"); tb.addWidget(self.empty)
        projects=SurfaceCard(); pb=QVBoxLayout(projects); pb.addWidget(QLabel("Project Overview")); self.project_list=QListWidget(); pb.addWidget(self.project_list); self.pinned=QLabel(); self.pinned.setObjectName("mutedText"); pb.addWidget(self.pinned); content.addWidget(tasks,0,0); content.addWidget(projects,0,1); content.setColumnStretch(0,2); content.setColumnStretch(1,1); layout.addLayout(content,1); self.refresh()
    def refresh(self)->None:
        data=self.queries.dashboard()
        for key,label in self.kpis.items(): label.setText(str(getattr(data,key)))
        self.task_list.clear()
        for row in data.due_this_week:
            item = QListWidgetItem(); item.setData(256, row.id); item.setSizeHint(ProgressDisplay().sizeHint())
            self.task_list.addItem(item)
            widget = QWidget(); line = QHBoxLayout(widget); line.setContentsMargins(4, 2, 4, 2)
            line.addWidget(QLabel(f"{row.title}   ·   {row.due_date:%a %d %b}"), 1)
            progress = ProgressDisplay(row.progress); progress.setFixedWidth(90); line.addWidget(progress)
            self.task_list.setItemWidget(item, widget)
        self.empty.setVisible(not data.due_this_week); self.project_list.clear()
        for _,name,progress,count,due in data.projects: self.project_list.addItem(f"{name}   {progress:.0f}%  ·  {count} tasks" + (f"  ·  {due:%d %b}" if due else ""))
        self.pinned.setText("Pinned: "+", ".join(name for _,name in data.pinned_projects) if data.pinned_projects else "No pinned projects")
