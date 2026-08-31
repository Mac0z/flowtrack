"""M4 application service/query integration coverage."""
from datetime import date, timedelta
import pytest
pytest.importorskip("sqlalchemy")
from sqlalchemy import create_engine
from flowtrack.application import TaskExecutionService, TaskFilters, TaskQueryService, TaskValidationError
from flowtrack.domain.enums import ProgressMode, TaskPriority, TaskStatus
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


@pytest.mark.parametrize(
    "child_status",
    [TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.WAITING],
)
def test_completion_write_path_rejects_unfinished_children(services, child_status):
    commands, queries = services
    parent = commands.create_task("Parent")
    child = commands.create_task("Child", parent_task_id=parent)
    commands.update_task(parent, progress_mode=ProgressMode.MANUAL, manual_progress=100)
    commands.update_task(child, status=child_status)

    with pytest.raises(TaskValidationError, match="unfinished child tasks"):
        commands.complete_task(parent)
    assert queries.task_detail(parent)["status"] is TaskStatus.NOT_STARTED


@pytest.mark.parametrize(
    "statuses",
    [[TaskStatus.CANCELLED], [TaskStatus.COMPLETE], [TaskStatus.COMPLETE, TaskStatus.CANCELLED]],
)
def test_completion_allows_only_finished_or_cancelled_children(services, statuses):
    commands, queries = services
    parent = commands.create_task("Parent")
    for index, status in enumerate(statuses):
        child = commands.create_task(f"Child {index}", parent_task_id=parent)
        commands.update_task(child, status=status)
    commands.complete_task(parent)
    assert queries.task_detail(parent)["status"] is TaskStatus.COMPLETE


def test_progress_and_status_remain_independent_and_feed_read_models(services):
    commands, queries = services
    automatic_leaf = commands.create_task("Automatic")
    manual_leaf = commands.create_task("Manual")
    commands.update_task(manual_leaf, progress_mode=ProgressMode.MANUAL, manual_progress=65)
    parent = commands.create_task("Parent")
    complete_child = commands.create_task("Done", parent_task_id=parent)
    open_child = commands.create_task("Open", parent_task_id=parent)
    commands.complete_task(complete_child)
    completed = commands.create_task("Completed")
    commands.complete_task(completed)

    rows = {row.id: row for row in queries.my_tasks()}
    assert rows[automatic_leaf].progress == 0
    assert rows[manual_leaf].progress == 65
    assert rows[parent].progress == 50
    assert rows[completed].progress == 100
    assert queries.task_detail(parent)["status"] is TaskStatus.NOT_STARTED
    assert queries.task_detail(manual_leaf)["status"] is TaskStatus.NOT_STARTED
    assert open_child in rows
