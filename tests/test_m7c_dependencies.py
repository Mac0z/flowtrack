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
    completed_predecessor = commands.create_task("Completed approval", project_id=project_id)
    current = commands.create_task("Build", project_id=project_id)
    successor = commands.create_task("Release")
    available_by_status = {
        status: commands.create_task(status.value)
        for status in (
            TaskStatus.NOT_STARTED,
            TaskStatus.IN_PROGRESS,
            TaskStatus.BLOCKED,
            TaskStatus.WAITING,
            TaskStatus.COMPLETE,
            TaskStatus.CANCELLED,
        )
    }
    for status, task_id in available_by_status.items():
        commands.update_task(task_id, status=status)
    commands.add_dependency(predecessor, current)
    commands.add_dependency(completed_predecessor, current)
    commands.add_dependency(current, successor)
    commands.update_task(completed_predecessor, status=TaskStatus.COMPLETE)
    commands.update_task(successor, status=TaskStatus.COMPLETE)

    data = queries.task_dependencies(current)

    assert [(row.task_id, row.title, row.project_name) for row in data.predecessors] == [
        (predecessor, "Approval", "Launch"),
        (completed_predecessor, "Completed approval", "Launch"),
    ]
    assert [(row.task_id, row.title, row.project_name) for row in data.successors] == [
        (successor, "Release", None)]
    choice_ids = {row.task_id for row in data.add_choices}
    for status in (
        TaskStatus.NOT_STARTED,
        TaskStatus.IN_PROGRESS,
        TaskStatus.BLOCKED,
        TaskStatus.WAITING,
    ):
        assert available_by_status[status] in choice_ids
    assert available_by_status[TaskStatus.COMPLETE] not in choice_ids
    assert available_by_status[TaskStatus.CANCELLED] not in choice_ids
    assert current not in choice_ids
    assert predecessor not in choice_ids
    assert data.predecessors[1].status is TaskStatus.COMPLETE
    assert data.successors[0].status is TaskStatus.COMPLETE


def test_dependency_connector_strokes_path_and_fills_only_arrowhead():
    from uuid import uuid4

    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    from flowtrack.ui.widgets.gantt_timeline import ConnectorGeometry
    from flowtrack.ui.widgets.gantt_view import paint_dependency_connector

    class RecordingPainter:
        def __init__(self):
            self.brush = None
            self.path_brush = None
            self.arrow_brush = None
            self.saved = 0
            self.restored = 0

        def save(self):
            self.saved += 1

        def restore(self):
            self.restored += 1

        def setPen(self, _pen):
            pass

        def setBrush(self, brush):
            self.brush = brush

        def drawPath(self, _path):
            self.path_brush = self.brush

        def drawPolygon(self, _polygon):
            self.arrow_brush = self.brush

    painter = RecordingPainter()
    colour = QColor("#778899")
    connector = ConnectorGeometry(uuid4(), uuid4(), ((10.0, 12.0), (20.0, 12.0), (20.0, 30.0)))

    paint_dependency_connector(painter, connector, colour)

    assert painter.path_brush is Qt.BrushStyle.NoBrush
    assert painter.arrow_brush == colour
    assert painter.brush is Qt.BrushStyle.NoBrush
    assert (painter.saved, painter.restored) == (1, 1)


def test_inspector_add_remove_order_refresh_and_signal(application, services, monkeypatch):
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
    monkeypatch.setattr(inspector, "confirm_dependency_removal", lambda _title: True)
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
