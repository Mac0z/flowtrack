"""Comprehensive unit tests for the M2 domain rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest

from flowtrack.domain.enums import ProgressMode, TaskStatus
from flowtrack.domain.services import (
    DependencyCycleError,
    HierarchyCycleError,
    calculate_project_progress,
    calculate_task_progress,
    completed_at_for_status,
    ensure_children_allow_completion,
    ensure_dependency_is_acyclic,
    ensure_valid_parent,
    is_cancelled,
    is_complete,
    is_overdue,
)


@dataclass
class TaskStub:
    status: TaskStatus = TaskStatus.NOT_STARTED
    progress_mode: ProgressMode = ProgressMode.AUTOMATIC
    manual_progress: int = 0
    children: list[TaskStub] = field(default_factory=list)
    parent_task_id: UUID | None = None


@dataclass
class ProjectStub:
    progress_mode: ProgressMode = ProgressMode.AUTOMATIC
    manual_progress: int = 0
    tasks: list[TaskStub] = field(default_factory=list)


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        (TaskStub(status=TaskStatus.COMPLETE), 100.0),
        (TaskStub(status=TaskStatus.IN_PROGRESS), 0.0),
        (TaskStub(progress_mode=ProgressMode.MANUAL, manual_progress=37), 37.0),
        (
            TaskStub(status=TaskStatus.COMPLETE, progress_mode=ProgressMode.MANUAL, manual_progress=12),
            100.0,
        ),
    ],
)
def test_leaf_progress(task: TaskStub, expected: float) -> None:
    assert calculate_task_progress(task) == expected


def test_nested_parent_uses_immediate_child_progress() -> None:
    nested_parent = TaskStub(children=[TaskStub(status=TaskStatus.COMPLETE), TaskStub()])
    root = TaskStub(children=[nested_parent, TaskStub(status=TaskStatus.COMPLETE)])

    assert calculate_task_progress(nested_parent) == 50.0
    assert calculate_task_progress(root) == 75.0


def test_manual_parent_overrides_children() -> None:
    parent = TaskStub(
        progress_mode=ProgressMode.MANUAL,
        manual_progress=23,
        children=[TaskStub(status=TaskStatus.COMPLETE)],
    )
    assert calculate_task_progress(parent) == 23.0


def test_cancelled_children_are_excluded_and_no_eligible_children_is_zero() -> None:
    complete = TaskStub(status=TaskStatus.COMPLETE)
    cancelled = TaskStub(status=TaskStatus.CANCELLED, progress_mode=ProgressMode.MANUAL, manual_progress=91)

    assert calculate_task_progress(TaskStub(children=[complete, cancelled])) == 100.0
    assert calculate_task_progress(TaskStub(children=[cancelled])) == 0.0


def test_project_automatic_progress_uses_only_top_level_non_cancelled_tasks() -> None:
    parent_id = uuid4()
    project = ProjectStub(
        tasks=[
            TaskStub(status=TaskStatus.COMPLETE),
            TaskStub(),
            TaskStub(status=TaskStatus.COMPLETE, parent_task_id=parent_id),
            TaskStub(status=TaskStatus.CANCELLED),
        ]
    )
    assert calculate_project_progress(project) == 50.0


def test_project_manual_progress_overrides_tasks() -> None:
    project = ProjectStub(
        progress_mode=ProgressMode.MANUAL,
        manual_progress=64,
        tasks=[TaskStub(status=TaskStatus.COMPLETE)],
    )
    assert calculate_project_progress(project) == 64.0


def test_project_without_eligible_tasks_is_zero() -> None:
    assert calculate_project_progress(ProjectStub(tasks=[TaskStub(status=TaskStatus.CANCELLED)])) == 0.0


@pytest.mark.parametrize("value", [-1, 101])
def test_invalid_manual_progress_is_rejected(value: int) -> None:
    with pytest.raises(ValueError, match="between 0 and 100"):
        calculate_task_progress(TaskStub(progress_mode=ProgressMode.MANUAL, manual_progress=value))


def test_status_and_completion_timestamp_semantics() -> None:
    first_completion = datetime(2026, 8, 1, tzinfo=timezone.utc)
    later = datetime(2026, 8, 2, tzinfo=timezone.utc)

    assert is_complete(TaskStatus.COMPLETE)
    assert not is_complete(TaskStatus.CANCELLED)
    assert is_cancelled(TaskStatus.CANCELLED)
    assert completed_at_for_status(TaskStatus.IN_PROGRESS, TaskStatus.COMPLETE, None, now=first_completion) == first_completion
    assert completed_at_for_status(TaskStatus.COMPLETE, TaskStatus.COMPLETE, first_completion, now=later) == first_completion
    assert completed_at_for_status(TaskStatus.COMPLETE, TaskStatus.IN_PROGRESS, first_completion, now=later) is None


@pytest.mark.parametrize(
    "child_status",
    [TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.WAITING],
)
def test_unfinished_active_child_blocks_parent_completion(child_status: TaskStatus) -> None:
    with pytest.raises(ValueError, match="unfinished child tasks"):
        ensure_children_allow_completion(TaskStatus.COMPLETE, [child_status])


@pytest.mark.parametrize(
    "child_statuses",
    [[TaskStatus.CANCELLED], [TaskStatus.COMPLETE], [TaskStatus.COMPLETE, TaskStatus.CANCELLED]],
)
def test_finished_or_cancelled_children_allow_parent_completion(child_statuses: list[TaskStatus]) -> None:
    ensure_children_allow_completion(TaskStatus.COMPLETE, child_statuses)


@pytest.mark.parametrize("status", [TaskStatus.COMPLETE, TaskStatus.CANCELLED])
def test_finished_or_cancelled_task_is_not_overdue(status: TaskStatus) -> None:
    assert not is_overdue(due_date=date(2026, 8, 1), status=status, today=date(2026, 8, 2))


@pytest.mark.parametrize("status", [TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.WAITING])
def test_open_statuses_are_overdue_after_due_calendar_date(status: TaskStatus) -> None:
    assert is_overdue(due_date=date(2026, 8, 1), status=status, today=date(2026, 8, 2))


def test_due_today_future_and_missing_due_date_are_not_overdue() -> None:
    today = date(2026, 8, 2)
    assert not is_overdue(due_date=today, status=TaskStatus.IN_PROGRESS, today=today)
    assert not is_overdue(due_date=date(2026, 8, 3), status=TaskStatus.IN_PROGRESS, today=today)
    assert not is_overdue(due_date=None, status=TaskStatus.IN_PROGRESS, today=today)


def test_hierarchy_rejects_self_and_indirect_descendant_parenting() -> None:
    root, child, grandchild = uuid4(), uuid4(), uuid4()
    parents = {root: None, child: root, grandchild: child}

    with pytest.raises(HierarchyCycleError):
        ensure_valid_parent(root, root, parents)
    with pytest.raises(HierarchyCycleError):
        ensure_valid_parent(root, grandchild, parents)


def test_deep_hierarchy_is_supported_without_recursion_limit() -> None:
    nodes = [uuid4() for _ in range(2_000)]
    parents = {nodes[0]: None, **{nodes[index]: nodes[index - 1] for index in range(1, len(nodes))}}

    ensure_valid_parent(uuid4(), nodes[-1], parents)
    with pytest.raises(HierarchyCycleError):
        ensure_valid_parent(nodes[0], nodes[-1], parents)


def test_valid_acyclic_dependency_graph() -> None:
    tasks = [uuid4() for _ in range(6)]
    dependencies = list(zip(tasks, tasks[1:]))
    ensure_dependency_is_acyclic(tasks[0], uuid4(), dependencies)


def test_direct_dependency_cycle_and_self_dependency_are_rejected() -> None:
    first, second = uuid4(), uuid4()
    with pytest.raises(DependencyCycleError):
        ensure_dependency_is_acyclic(second, first, [(first, second)])
    with pytest.raises(DependencyCycleError, match="itself"):
        ensure_dependency_is_acyclic(first, first, [])


def test_indirect_deep_dependency_cycle_is_rejected() -> None:
    tasks = [uuid4() for _ in range(2_000)]
    dependencies = list(zip(tasks, tasks[1:]))
    with pytest.raises(DependencyCycleError):
        ensure_dependency_is_acyclic(tasks[-1], tasks[0], dependencies)
