"""Small local owner and reusable-tag management surface."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox,QDialog,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,QPushButton,QTabWidget,QVBoxLayout,QWidget
from flowtrack.application.task_execution import TaskExecutionService,TaskValidationError
from flowtrack.application.task_queries import TaskQueryService

class PeopleTagsDialog(QDialog):
    changed=Signal()
    def __init__(self,service:TaskExecutionService,queries:TaskQueryService,parent=None)->None:
        super().__init__(parent);self.service,self.queries=service,queries;self.setWindowTitle("Owners & Tags");self.resize(520,430);tabs=QTabWidget();layout=QVBoxLayout(self);layout.addWidget(tabs)
        owners=QWidget();ob=QVBoxLayout(owners);self.owner_list=QListWidget();self.owner_list.itemSelectionChanged.connect(lambda:self.owner_name.setText(self.owner_list.currentItem().text().split(" ·")[0]) if self.owner_list.currentItem() else None);ob.addWidget(self.owner_list);of=QHBoxLayout();self.owner_name=QLineEdit();self.owner_name.setPlaceholderText("Owner name");add_owner=QPushButton("Add owner");add_owner.clicked.connect(self.add_owner);rename_owner=QPushButton("Rename");rename_owner.clicked.connect(self.rename_owner);of.addWidget(self.owner_name);of.addWidget(add_owner);of.addWidget(rename_owner);ob.addLayout(of);inactive=QPushButton("Mark selected inactive");inactive.clicked.connect(self.deactivate_owner);ob.addWidget(inactive);tabs.addTab(owners,"Owners")
        tags=QWidget();tb=QVBoxLayout(tags);self.tag_list=QListWidget();self.tag_list.itemSelectionChanged.connect(lambda:self.tag_name.setText(self.tag_list.currentItem().text()) if self.tag_list.currentItem() else None);tb.addWidget(self.tag_list);tf=QHBoxLayout();self.tag_name=QLineEdit();self.tag_name.setPlaceholderText("Tag name");add_tag=QPushButton("Add tag");add_tag.clicked.connect(self.add_tag);rename_tag=QPushButton("Rename");rename_tag.clicked.connect(self.rename_tag);tf.addWidget(self.tag_name);tf.addWidget(add_tag);tf.addWidget(rename_tag);tb.addLayout(tf);tabs.addTab(tags,"Tags");self.error=QLabel();self.error.setObjectName("dangerText");layout.addWidget(self.error);self.refresh()
    def refresh(self)->None:
        self.owner_list.clear()
        for id_,name,active in self.queries.owners():self.owner_list.addItem(name+("" if active else " · inactive"));self.owner_list.item(self.owner_list.count()-1).setData(256,id_)
        self.tag_list.clear()
        for id_,name in self.queries.tags():self.tag_list.addItem(name);self.tag_list.item(self.tag_list.count()-1).setData(256,id_)
    def add_owner(self)->None:
        try:self.service.create_owner(self.owner_name.text())
        except TaskValidationError as e:self.error.setText(str(e));return
        self.owner_name.clear();self.error.clear();self.refresh();self.changed.emit()
    def deactivate_owner(self)->None:
        item=self.owner_list.currentItem()
        if item:self.service.update_owner(item.data(256),is_active=False);self.refresh();self.changed.emit()
    def rename_owner(self)->None:
        item=self.owner_list.currentItem()
        if item:self.service.update_owner(item.data(256),name=self.owner_name.text().strip());self.refresh();self.changed.emit()
    def add_tag(self)->None:
        try:self.service.create_tag(self.tag_name.text())
        except TaskValidationError as e:self.error.setText(str(e));return
        self.tag_name.clear();self.error.clear();self.refresh();self.changed.emit()
    def rename_tag(self)->None:
        item=self.tag_list.currentItem()
        if not item:return
        try:self.service.update_tag(item.data(256),name=self.tag_name.text())
        except TaskValidationError as e:self.error.setText(str(e));return
        self.refresh();self.changed.emit()
