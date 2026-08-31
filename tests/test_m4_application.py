"""M4 application service/query integration coverage."""
from datetime import date, timedelta
import pytest
pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine
from flowtrack.application import TaskExecutionService, TaskFilters, TaskQueryService, TaskValidationError
from flowtrack.domain.enums import TaskPriority, TaskStatus
from flowtrack.persistence.database import session_factory
from flowtrack.persistence.models import Base

@pytest.fixture
def services():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    return TaskExecutionService(factory), TaskQueryService(factory)

def test_create_search_complete_reopen_and_cancel(services):
    commands, queries = services
    task = commands.create_task("Write brief", description="Quarterly operations")
    assert queries.my_tasks(search="OPERATIONS")[0].id == task
    commands.complete_task(task)
    detail = queries.task_detail(task)
    assert detail["status"] is TaskStatus.COMPLETE and detail["progress"] == 100
    commands.complete_task(task, False)
    assert queries.task_detail(task)["status"] is TaskStatus.NOT_STARTED
    commands.cancel_task(task)
    assert queries.task_detail(task)["status"] is TaskStatus.CANCELLED

def test_sorting_filters_owners_tags_and_hierarchy(services):
    commands, queries = services
    today = date.today(); owner = commands.create_owner("Alex"); tag = commands.create_tag("Focus")
    late = commands.create_task("Late", owner_id=owner, due_date=today-timedelta(days=1), priority=TaskPriority.LOW)
    soon = commands.create_task("Soon", due_date=today+timedelta(days=2), priority=TaskPriority.HIGH)
    commands.set_tags(soon, [tag])
    assert [r.id for r in queries.my_tasks(today=today)][:2] == [late, soon]
    assert queries.my_tasks(filters=TaskFilters(owner_id=owner))[0].id == late
    assert queries.my_tasks(filters=TaskFilters(tag_ids=frozenset([tag])))[0].id == soon
    child = commands.create_task("Child", parent_task_id=soon)
    assert queries.task_detail(soon)["children"][0][0] == child
    with pytest.raises(Exception): commands.update_task(soon, parent_task_id=child)

def test_validation_dashboard_and_deletion_guard(services):
    commands, queries = services
    with pytest.raises(TaskValidationError): commands.create_task("  ")
    parent = commands.create_task("Parent"); commands.create_task("Child", parent_task_id=parent)
    with pytest.raises(TaskValidationError): commands.delete_task(parent)
    commands.delete_task(parent, allow_with_children=True)
    assert queries.dashboard().active_projects == 0
