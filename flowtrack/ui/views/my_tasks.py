"""Compact cross-project task execution list."""
from uuid import UUID
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from flowtrack.application.task_execution import TaskExecutionService, TaskValidationError
from flowtrack.application.task_queries import TaskFilters, TaskQueryService
from flowtrack.domain.enums import TaskPriority, TaskStatus
from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.ui.widgets import ProgressDisplay, SectionHeading
from flowtrack.ui.theme.dark import DARK_THEME
from flowtrack.ui.theme.status import status_color

class MyTasksView(QWidget):
    task_selected=Signal(object); data_changed=Signal()
    def __init__(self, service:TaskExecutionService, queries:TaskQueryService, settings:ApplicationSettings,parent=None)->None:
        super().__init__(parent); self.service,self.queries,self.settings=service,queries,settings; layout=QVBoxLayout(self); layout.setContentsMargins(24,20,24,20); layout.setSpacing(10); layout.addWidget(SectionHeading("My Tasks","Work across projects and standalone tasks"))
        bar=QHBoxLayout(); self.search=QLineEdit(); self.search.setPlaceholderText("Search title or description…"); self.status=QComboBox(); self.priority=QComboBox(); self.project=QComboBox(); self.owner=QComboBox(); self.tag=QComboBox(); self.date_window=QComboBox()
        self.status.addItem("All statuses",None); self.priority.addItem("All priorities",None)
        for v in TaskStatus:self.status.addItem(v.value.replace("_"," ").title(),v.value)
        for v in TaskPriority:self.priority.addItem(v.value.title(),v.value)
        for text,data in (("Any date",None),("Overdue","overdue"),("Due this week","week"),("No due date","none")):self.date_window.addItem(text,data)
        reset=QPushButton("Reset"); reset.clicked.connect(self.reset_filters)
        for w in (self.search,self.status,self.priority,self.project,self.owner,self.tag,self.date_window,reset):bar.addWidget(w)
        bar.setStretch(0,2); layout.addLayout(bar); self.table=QTableWidget(0,8); self.table.setHorizontalHeaderLabels(["Done","Task","Status","Priority","Project","Owner","Due","Progress"]); self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.table.verticalHeader().setDefaultSectionSize(34); self.table.cellDoubleClicked.connect(lambda row,_:self.task_selected.emit(self.table.item(row,1).data(256))); self.table.cellClicked.connect(self._clicked); layout.addWidget(self.table,1)
        self.search.textChanged.connect(self.refresh)
        for combo in (self.status,self.priority,self.project,self.owner,self.tag,self.date_window):combo.currentIndexChanged.connect(self.refresh)
        self._options(); self._restore(); self.refresh()
    def _options(self)->None:
        for combo,label in ((self.project,"All projects"),(self.owner,"All owners"),(self.tag,"All tags")):combo.addItem(label,None)
        for id_,name in self.queries.projects():self.project.addItem(name,id_)
        for id_,name,_ in self.queries.owners():self.owner.addItem(name,id_)
        for id_,name in self.queries.tags():self.tag.addItem(name,id_)
    def _restore(self)->None:
        data=self.settings.my_tasks_filters
        for combo,key in ((self.status,"status"),(self.priority,"priority"),(self.project,"project"),(self.owner,"owner"),(self.tag,"tag"),(self.date_window,"date")):
            value=data.get(key); index=next((i for i in range(combo.count()) if str(combo.itemData(i))==str(value)),0); combo.setCurrentIndex(index)
    def _filters(self)->TaskFilters:
        from datetime import date,timedelta
        today=date.today(); window=self.date_window.currentData(); due_from=due_to=None
        if window=="overdue":due_to=today-timedelta(days=1)
        elif window=="week":due_from=today; due_to=today+timedelta(days=6-today.weekday())
        status = self.status.currentData(); priority = self.priority.currentData()
        return TaskFilters(frozenset([TaskStatus(status)]) if status else frozenset(),frozenset([TaskPriority(priority)]) if priority else frozenset(),self.project.currentData(),self.owner.currentData(),frozenset([self.tag.currentData()]) if self.tag.currentData() else frozenset(),due_from,due_to)
    def refresh(self,*_)->None:
        rows=self.queries.my_tasks(search=self.search.text(),filters=self._filters()); self.table.setRowCount(len(rows))
        for r,row in enumerate(rows):
            values=("✓" if row.status is TaskStatus.COMPLETE else "○",row.title,row.status.value.replace("_"," ").title(),row.priority.value.title(),row.project_name or "—",row.owner_name or "—",row.due_date.isoformat() if row.due_date else "—")
            for c,value in enumerate(values):
                item=QTableWidgetItem(value); item.setData(256,row.id)
                if c == 2:
                    item.setForeground(QColor(status_color(DARK_THEME, row.status)))
                    font = item.font(); font.setWeight(QFont.Weight.Medium); item.setFont(font)
                elif row.status in (TaskStatus.COMPLETE, TaskStatus.CANCELLED):
                    item.setForeground(QColor(DARK_THEME.colors.text_muted))
                self.table.setItem(r,c,item)
            self.table.setCellWidget(r, 7, ProgressDisplay(row.progress))
        self.table.resizeColumnsToContents(); self.settings.my_tasks_filters={"status":str(self.status.currentData()) if self.status.currentData() else None,"priority":str(self.priority.currentData()) if self.priority.currentData() else None,"project":str(self.project.currentData()) if self.project.currentData() else None,"owner":str(self.owner.currentData()) if self.owner.currentData() else None,"tag":str(self.tag.currentData()) if self.tag.currentData() else None,"date":self.date_window.currentData()}
    def _clicked(self,row:int,column:int)->None:
        if column==0:
            item=self.table.item(row,0)
            try:
                self.service.complete_task(item.data(256),item.text()!="✓")
            except TaskValidationError:
                QMessageBox.warning(self, "Cannot complete task", "Task cannot be completed while it has unfinished child tasks. Complete or cancel the remaining child tasks first.")
                return
            self.refresh(); self.data_changed.emit()
    def focus_search(self)->None:self.search.setFocus(); self.search.selectAll()
    def reset_filters(self)->None:
        self.search.clear()
        for combo in (self.status,self.priority,self.project,self.owner,self.tag,self.date_window):combo.setCurrentIndex(0)
