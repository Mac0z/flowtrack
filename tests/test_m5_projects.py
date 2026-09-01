"""Application-level coverage for M5 project workflows and hierarchy."""
from datetime import date
from sqlalchemy import create_engine
from flowtrack.application.projects import ProjectQueryService, ProjectService, ProjectValidationError
from flowtrack.application.task_execution import TaskExecutionService
from flowtrack.domain.enums import ProgressMode, ProjectStatus, TaskStatus
from flowtrack.persistence.database import session_factory
from flowtrack.persistence.models import Base, Task

def services():
    engine=create_engine("sqlite+pysqlite:///:memory:"); Base.metadata.create_all(engine); factory=session_factory(engine)
    return ProjectService(factory),ProjectQueryService(factory),TaskExecutionService(factory),factory

def test_create_edit_validation_and_manual_progress():
    commands,queries,_,_=services(); project_id=commands.create_project(" Launch ",description="Initial")
    project=queries.project_detail(project_id); assert project and project.name=="Launch" and project.status is ProjectStatus.PLANNED
    commands.update_project(project_id,name="Release",progress_mode=ProgressMode.MANUAL,manual_progress=63,is_pinned=True)
    project=queries.project_detail(project_id); assert project and (project.name,project.progress,project.is_pinned)==("Release",63,True)
    import pytest
    with pytest.raises(ProjectValidationError,match="Name is required"):commands.create_project("  ")
    with pytest.raises(ProjectValidationError,match="between 0 and 100"):commands.update_project(project_id,manual_progress=101)

def test_metrics_automatic_progress_and_project_task_exclusion():
    commands,queries,tasks,_=services(); project_id=commands.create_project("Delivery",status=ProjectStatus.ACTIVE)
    parent=tasks.create_task("Parent",project_id=project_id,due_date=date(2026,1,1)); child=tasks.create_task("Child",parent_task_id=parent); tasks.complete_task(child)
    second=tasks.create_task("Second",project_id=project_id); tasks.update_task(second,progress_mode=ProgressMode.MANUAL,manual_progress=50,status=TaskStatus.BLOCKED)
    tasks.create_task("Standalone"); other=commands.create_project("Other"); tasks.create_task("Other task",project_id=other)
    summary=queries.project_detail(project_id,today=date(2026,2,1)); assert summary
    assert summary.progress==75 and summary.task_count==3 and summary.completed_count==1 and summary.overdue_count==1 and summary.blocked_count==1
    assert [row.title for row in queries.project_tasks(project_id)]==["Parent","Child","Second"]

def test_hierarchy_is_depth_first_and_siblings_use_sort_order():
    commands,queries,tasks,factory=services(); project=commands.create_project("Nested")
    root=tasks.create_task("Root",project_id=project); late=tasks.create_task("Late",parent_task_id=root); early=tasks.create_task("Early",parent_task_id=root); grand=tasks.create_task("Grand",parent_task_id=early)
    with factory.begin() as session:
        session.get(Task,late).sort_order=20; session.get(Task,early).sort_order=10
    rows=queries.project_tasks(project)
    assert [(row.title,row.hierarchy_depth) for row in rows]==[("Root",0),("Early",1),("Grand",2),("Late",1)]

def test_pin_archive_filter_and_stable_sorting():
    commands,queries,_,_=services(); planned=commands.create_project("Zulu"); active=commands.create_project("Alpha",status=ProjectStatus.ACTIVE); pinned=commands.create_project("Pinned",is_pinned=True); archived=commands.create_project("Archive",is_pinned=True)
    assert [p.id for p in queries.list_projects()]==[archived,pinned,active,planned]
    commands.archive_project(archived)
    assert archived not in [p.id for p in queries.list_projects()]
    assert archived in [p.id for p in queries.list_projects(include_archived=True)]
    assert archived not in [p.id for p in queries.pinned_projects()]
    assert queries.project_detail(archived).is_pinned
    commands.unarchive_project(archived); assert queries.project_detail(archived).status is ProjectStatus.PLANNED
    commands.set_pinned(pinned,False); assert pinned not in [p.id for p in queries.pinned_projects()]
