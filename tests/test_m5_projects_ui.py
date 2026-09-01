"""Focused, non-pixel M5 project UI workflows."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from sqlalchemy import create_engine
from flowtrack.application.projects import ProjectQueryService, ProjectService
from flowtrack.application.task_execution import TaskExecutionService
from flowtrack.domain.enums import ProjectStatus
from flowtrack.persistence.database import session_factory
from flowtrack.persistence.models import Base
from flowtrack.ui.views.projects import ProjectsView

def make_view():
    engine=create_engine("sqlite+pysqlite:///:memory:"); Base.metadata.create_all(engine); factory=session_factory(engine)
    projects=ProjectService(factory); queries=ProjectQueryService(factory); tasks=TaskExecutionService(factory)
    return ProjectsView(projects,queries,tasks),projects,queries,tasks

def test_cards_open_overview_and_archived_filter(application):
    view,projects,_,_=make_view(); project=projects.create_project("Launch",description="Ship it")
    view.refresh(); assert view.cards.count()==1
    view.open_project(project); assert view.heading.title.text()=="Launch" and view.description.text()=="Ship it"
    projects.archive_project(project); view.show_projects(); assert view.cards.count()==0
    view.show_archived.setChecked(True); assert view.cards.count()==1

def test_project_list_hierarchy_activation_and_new_task_context(application):
    view,projects,_,tasks=make_view(); project=projects.create_project("Nested")
    parent=tasks.create_task("Parent",project_id=project); child=tasks.create_task("Child",parent_task_id=parent)
    view.open_project(project); assert view.table.rowCount()==2
    assert view.table.item(1,0).data(257)==1
    activated=[]; view.task_selected.connect(activated.append); view._activate_task(1,0); assert activated==[child]
    requested=[]; view.new_task_requested.connect(requested.append); view._new_task(); assert requested==[project]

def test_pin_and_archive_emit_refresh_signal(application):
    view,projects,queries,_=make_view(); project=projects.create_project("Pinned")
    changes=[]; view.project_changed.connect(lambda:changes.append(True)); view.open_project(project)
    view._toggle_pin(); assert queries.project_detail(project).is_pinned
    view._archive(); assert queries.project_detail(project).status is ProjectStatus.ARCHIVED
    assert len(changes)==2
