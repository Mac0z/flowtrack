"""M7C dependency-management application, query, and inspector coverage."""

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine, func, select

from flowtrack.application.task_execution import TaskExecutionService, TaskValidationError
from flowtrack.application.task_queries import TaskQueryService
from flowtrack.domain.enums import TaskStatus
from flowtrack.persistence.database import session_factory
from flowtrack.persistence.models import Base, Dependency


@pytest.fixture
def services():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    return TaskExecutionService(factory), TaskQueryService(factory), factory


def test_dependencies_are_cycle_safe_duplicate_safe_and_removable(services):
    commands, _, factory = services
    first = commands.create_task("First")
    second = commands.create_task("Second")
    third = commands.create_task("Third")
    unrelated = commands.create_task("Unrelated")

    dependency_id = commands.add_dependency(first, second)
    assert commands.add_dependency(first, second) == dependency_id
    commands.add_dependency(second, third)
    commands.add_dependency(first, unrelated)

    with pytest.raises(TaskValidationError, match="itself"):
        commands.add_dependency(first, first)
    with pytest.raises(TaskValidationError, match="circular"):
        commands.add_dependency(second, first)
    with pytest.raises(TaskValidationError, match="circular"):
        commands.add_dependency(third, first)

    commands.remove_dependency(first, second)
    commands.remove_dependency(first, second)  # Idempotent for a stale inspector.
    with factory() as session:
        edges = set(session.execute(select(
            Dependency.predecessor_task_id, Dependency.successor_task_id)).all())
        assert (first, second) not in edges
        assert edges == {(second, third), (first, unrelated)}
        assert session.scalar(select(func.count()).select_from(Dependency)) == 2


def test_dependency_read_model_has_context_and_filtered_choices(services):
    commands, queries, _ = services
    from flowtrack.application.projects import ProjectService

    project_id = ProjectService(commands._factory).create_project("Launch")
    predecessor = commands.create_task("Approval", project_id=project_id)
    current = commands.create_task("Build", project_id=project_id)
    successor = commands.create_task("Release")
    available = commands.create_task("Research")
    cancelled = commands.create_task("Discarded")
    commands.update_task(cancelled, status=TaskStatus.CANCELLED)
    commands.add_dependency(predecessor, current)
    commands.add_dependency(current, successor)

    data = queries.task_dependencies(current)

    assert [(row.task_id, row.title, row.project_name) for row in data.predecessors] == [
        (predecessor, "Approval", "Launch")]
    assert [(row.task_id, row.title, row.project_name) for row in data.successors] == [
        (successor, "Release", None)]
    choice_ids = {row.task_id for row in data.add_choices}
    assert available in choice_ids
    assert successor in choice_ids
    assert current not in choice_ids
    assert predecessor not in choice_ids
    assert cancelled not in choice_ids


def test_inspector_add_remove_order_refresh_and_signal(application, services):
    pytest.importorskip("PySide6")
    from flowtrack.ui.widgets.task_inspector import TaskInspector

    commands, queries, _ = services
    predecessor = commands.create_task("Approval")
    current = commands.create_task("Build")
    successor = commands.create_task("Release")
    commands.add_dependency(current, successor)
    inspector = TaskInspector(commands, queries)
    changes: list[bool] = []
    inspector.saved.connect(lambda: changes.append(True))
    inspector.load_task(current)

    assert inspector.predecessors_layout.count() == 0
    assert inspector.successors_layout.count() == 1
    inspector.dependency_picker.setCurrentIndex(
        inspector.dependency_picker.findData(str(predecessor)))
    inspector.add_selected_dependency()

    assert inspector.predecessors_layout.count() == 1
    assert queries.task_dependencies(current).predecessors[0].task_id == predecessor
    inspector.remove_predecessor(predecessor)
    assert inspector.predecessors_layout.count() == 0
    assert queries.task_dependencies(current).predecessors == ()
    assert len(changes) == 2


def test_inspector_displays_cycle_error_without_changing_rows(application, services):
    pytest.importorskip("PySide6")
    from flowtrack.ui.widgets.task_inspector import TaskInspector

    commands, queries, _ = services
    current = commands.create_task("Current")
    would_cycle = commands.create_task("Would cycle")
    commands.add_dependency(current, would_cycle)
    inspector = TaskInspector(commands, queries)
    inspector.load_task(current)
    inspector.dependency_picker.setCurrentIndex(
        inspector.dependency_picker.findData(str(would_cycle)))

    inspector.add_selected_dependency()

    assert "circular dependency" in inspector.error.text()
    assert inspector.predecessors_layout.count() == 0
