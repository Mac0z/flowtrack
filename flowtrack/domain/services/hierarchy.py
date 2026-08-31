"""Rules for the recursive task hierarchy."""

from collections.abc import Mapping
from uuid import UUID


class HierarchyCycleError(ValueError):
    """Raised when a parent assignment would make the hierarchy cyclic."""


def ensure_valid_parent(
    task_id: UUID,
    parent_task_id: UUID | None,
    parent_by_task: Mapping[UUID, UUID | None],
) -> None:
    """Reject self-parenting and assignment beneath any descendant.

    ``parent_by_task`` may contain an arbitrarily deep hierarchy. Missing keys
    are treated as roots so callers can validate a newly-created task.
    """
    current = parent_task_id
    visited: set[UUID] = set()
    while current is not None:
        if current == task_id:
            raise HierarchyCycleError("a task cannot be its own ancestor")
        if current in visited:
            raise HierarchyCycleError("the existing task hierarchy contains a cycle")
        visited.add(current)
        current = parent_by_task.get(current)
