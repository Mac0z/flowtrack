"""Focused, non-pixel tests for the M6A project Kanban board."""
import os
from datetime import date, timedelta
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from sqlalchemy import create_engine
from flowtrack.application.projects import ProjectQueryService, ProjectService
from flowtrack.application.task_execution import TaskExecutionService
from flowtrack.domain.enums import TaskPriority, TaskStatus
from flowtrack.persistence.database import session_factory
from flowtrack.persistence.models import Base
from flowtrack.ui.widgets.kanban_board import ProjectBoard, WORKING_STATUSES
from flowtrack.ui.views.projects import ProjectsView


def make_services():
    engine=create_engine("sqlite+pysqlite:///:memory:"); Base.metadata.create_all(engine); factory=session_factory(engine)
    return ProjectService(factory),ProjectQueryService(factory),TaskExecutionService(factory)


def item_ids(board,status):
    column=board.columns[status]
    return [column.item(index).data(256) for index in range(column.count())]


def test_board_columns_disable_horizontal_scrolling(application):
    projects,queries,tasks=make_services(); board=ProjectBoard(tasks,queries)
    assert all(
        column.horizontalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        for column in board.columns.values()
    )


def test_board_has_working_columns_and_groups_same_task_ids(application):
    projects,queries,tasks=make_services(); project=projects.create_project("Launch")
    expected={}
    for status in (*WORKING_STATUSES,TaskStatus.CANCELLED):
        task_id=tasks.create_task(status.value,project_id=project)
        tasks.update_task(task_id,status=status); expected[status]=task_id
    board=ProjectBoard(tasks,queries); board.set_project(project)
    assert tuple(board.columns) == (*WORKING_STATUSES,TaskStatus.CANCELLED)
    for status,task_id in expected.items():assert item_ids(board,status)==[task_id]
    assert not board.column_frames[TaskStatus.CANCELLED].isVisible()
    board.show_cancelled.setChecked(True)
    assert not board.column_frames[TaskStatus.CANCELLED].isHidden()
    assert "1" in board.headings[TaskStatus.COMPLETE].text()


def test_move_uses_service_refreshes_immediately_and_emits(application,monkeypatch):
    projects,queries,tasks=make_services(); project=projects.create_project("Launch"); task_id=tasks.create_task("Ship",project_id=project)
    board=ProjectBoard(tasks,queries); board.set_project(project); calls=[]; changed=[]
    original=tasks.update_task
    def tracked(identifier,**changes):calls.append((identifier,changes));original(identifier,**changes)
    monkeypatch.setattr(tasks,"update_task",tracked); board.data_changed.connect(lambda:changed.append(True))
    assert board.move_task(task_id,TaskStatus.IN_PROGRESS)
    assert calls==[(task_id,{"status":TaskStatus.IN_PROGRESS})] and changed==[True]
    assert item_ids(board,TaskStatus.NOT_STARTED)==[]
    assert item_ids(board,TaskStatus.IN_PROGRESS)==[task_id]
    assert queries.project_tasks(project)[0].id==task_id


def test_card_activation_and_child_context_and_presentation(application):
    projects,queries,tasks=make_services(); project=projects.create_project("Launch")
    parent=tasks.create_task("Release",project_id=project); child=tasks.create_task("Notes",parent_task_id=parent,owner_id=None,due_date=date.today()-timedelta(days=1),priority=TaskPriority.HIGH)
    board=ProjectBoard(tasks,queries); board.set_project(project); opened=[]; board.task_activated.connect(opened.append)
    item=board.columns[TaskStatus.NOT_STARTED].item(1); board.columns[TaskStatus.NOT_STARTED].itemClicked.emit(item)
    assert opened==[child]
    card=board.columns[TaskStatus.NOT_STARTED].itemWidget(item)
    assert any("Release" in label.text() for label in card.findChildren(type(board.error)))
    assert "Overdue" in " ".join(label.text() for label in card.findChildren(type(board.error)))


def test_project_board_change_refreshes_overview_list_and_outer_views(application):
    projects,queries,tasks=make_services(); project=projects.create_project("Launch"); task_id=tasks.create_task("Ship",project_id=project)
    view=ProjectsView(projects,queries,tasks); changes=[]; view.project_changed.connect(lambda:changes.append(True)); view.open_project(project)
    assert view.board.move_task(task_id,TaskStatus.COMPLETE)
    assert changes==[True]
    assert view.table.item(0,1).text()=="Complete"
    assert "Completed:</b> 1" in view.metrics.text()
    assert view.cards.count()==1  # project landing data is refreshed too
