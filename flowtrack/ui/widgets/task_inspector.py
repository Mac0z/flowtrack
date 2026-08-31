"""Right-hand task inspector for detailed M4 edits."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QAbstractItemView,QComboBox,QDateEdit,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,QPlainTextEdit,QProgressBar,QPushButton,QVBoxLayout,QWidget
from flowtrack.application.task_execution import TaskExecutionService,TaskValidationError
from flowtrack.application.task_queries import TaskQueryService
from flowtrack.domain.enums import TaskPriority,TaskStatus

class TaskInspector(QWidget):
    closed=Signal(); saved=Signal(); deleted=Signal()
    def __init__(self,service:TaskExecutionService,queries:TaskQueryService,parent=None)->None:
        super().__init__(parent); self.service,self.queries=service,queries; self.task_id=None; self.setFixedWidth(390); layout=QVBoxLayout(self); top=QHBoxLayout(); top.addWidget(QLabel("TASK INSPECTOR")); close=QPushButton("×");close.clicked.connect(self.close_inspector);top.addWidget(close);layout.addLayout(top); form=QFormLayout(); self.title=QLineEdit();self.description=QPlainTextEdit();self.description.setMaximumHeight(90);self.status=QComboBox();self.priority=QComboBox();self.owner=QComboBox();self.start=QDateEdit();self.due=QDateEdit();self.progress=QProgressBar();self.tags=QListWidget();self.tags.setMaximumHeight(80);self.tags.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection);self.children=QLabel();self.dependencies=QLabel();
        for v in TaskStatus:self.status.addItem(v.value.replace("_"," ").title(),v)
        for v in TaskPriority:self.priority.addItem(v.value.title(),v)
        for field in (self.start,self.due):field.setCalendarPopup(True);field.setMinimumDate(field.minimumDate());field.setSpecialValueText("None")
        for label,w in (("Title",self.title),("Description",self.description),("Status",self.status),("Priority",self.priority),("Owner",self.owner),("Start",self.start),("Due",self.due),("Progress",self.progress),("Tags",self.tags),("Children",self.children),("Dependencies",self.dependencies)):form.addRow(label,w)
        layout.addLayout(form); self.error=QLabel();self.error.setObjectName("dangerText");layout.addWidget(self.error); buttons=QHBoxLayout();save=QPushButton("Save");save.clicked.connect(self.save);child=QPushButton("Add child");child.clicked.connect(self.add_child);delete=QPushButton("Delete…");delete.clicked.connect(self.request_delete);buttons.addWidget(save);buttons.addWidget(child);buttons.addWidget(delete);layout.addLayout(buttons);layout.addStretch();self.hide()
    def load_task(self,task_id)->None:
        detail=self.queries.task_detail(task_id)
        if not detail:return
        self.task_id=task_id;self.title.setText(detail["title"]);self.description.setPlainText(detail["description"]);self.status.setCurrentIndex(self.status.findData(detail["status"]));self.priority.setCurrentIndex(self.priority.findData(detail["priority"]));self.owner.clear();self.owner.addItem("Unassigned",None)
        for id_,name,_ in self.queries.owners(True):self.owner.addItem(name,id_)
        self.owner.setCurrentIndex(max(0,self.owner.findData(detail["owner_id"])));self.progress.setValue(round(detail["progress"]));self.tags.clear();selected={id_ for id_,_ in detail["tags"]}
        for id_,name in self.queries.tags():self.tags.addItem(name);item=self.tags.item(self.tags.count()-1);item.setData(256,id_);item.setSelected(id_ in selected)
        self.children.setText("\n".join(n for _,n,_ in detail["children"]) or "None");self.dependencies.setText("\n".join(n for _,n in detail["dependencies"]) or "None");self.show()
    def save(self)->None:
        try:self.service.update_task(self.task_id,title=self.title.text(),description=self.description.toPlainText(),status=self.status.currentData(),priority=self.priority.currentData(),owner_id=self.owner.currentData());self.service.set_tags(self.task_id,[item.data(256) for item in self.tags.selectedItems()])
        except TaskValidationError as e:self.error.setText(str(e));return
        self.error.clear();self.saved.emit();self.load_task(self.task_id)
    def add_child(self)->None:
        try:child=self.service.create_task("New child task",parent_task_id=self.task_id)
        except TaskValidationError as e:self.error.setText(str(e));return
        self.saved.emit();self.load_task(child)
    def request_delete(self)->None:self.deleted.emit()
    def close_inspector(self)->None:self.hide();self.closed.emit()
