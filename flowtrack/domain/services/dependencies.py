"""Finish-to-Start dependency graph rules."""

from collections.abc import Iterable
from uuid import UUID


class DependencyCycleError(ValueError):
    """Raised when a dependency would create a directed cycle."""


def ensure_dependency_is_acyclic(
    predecessor_task_id: UUID,
    successor_task_id: UUID,
    dependencies: Iterable[tuple[UUID, UUID]],
) -> None:
    """Reject a proposed predecessor-to-successor edge if it creates a cycle."""
    if predecessor_task_id == successor_task_id:
        raise DependencyCycleError("a task cannot depend on itself")

    successors: dict[UUID, set[UUID]] = {}
    for predecessor, successor in dependencies:
        successors.setdefault(predecessor, set()).add(successor)

    pending = [successor_task_id]
    visited: set[UUID] = set()
    while pending:
        task_id = pending.pop()
        if task_id == predecessor_task_id:
            raise DependencyCycleError("dependency would create a cycle")
        if task_id not in visited:
            visited.add(task_id)
            pending.extend(successors.get(task_id, ()))
