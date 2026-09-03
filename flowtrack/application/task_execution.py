"""Transactional application service for M4 task execution workflows."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from flowtrack.domain.enums import ProgressMode, TaskPriority, TaskStatus
from flowtrack.domain.services import (
    IncompleteChildrenError,
    completed_at_for_status,
    ensure_children_allow_completion,
    ensure_dependency_is_acyclic,
    ensure_valid_parent,
)
from flowtrack.persistence.database import transaction
from flowtrack.persistence.models import Dependency, Owner, Tag, Task
from flowtrack.persistence.repositories import DependencyRepository, OwnerRepository, TagRepository, TaskRepository


class TaskValidationError(ValueError):
    """A user-correctable task input error."""


class TaskExecutionService:
    """Coordinates repositories and domain rules behind a transaction boundary."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def create_task(self, title: str, *, project_id: UUID | None = None,
                    parent_task_id: UUID | None = None, owner_id: UUID | None = None,
                    start_date: date | None = None,
                    due_date: date | None = None, priority: TaskPriority = TaskPriority.MEDIUM,
                    description: str | None = None) -> UUID:
        clean_title = title.strip()
        if not clean_title:
            raise TaskValidationError("Title is required")
        if start_date is not None and due_date is not None and start_date > due_date:
            raise TaskValidationError("Start date cannot be later than due date")
        with transaction(self._factory) as session:
            if parent_task_id is not None:
                parent = TaskRepository(session).get(parent_task_id)
                if parent is None:
                    raise TaskValidationError("Parent task does not exist")
                project_id = parent.project_id
            task = Task(title=clean_title, description=(description or "").strip() or None,
                        project_id=project_id, parent_task_id=parent_task_id,
                        owner_id=owner_id, start_date=start_date, due_date=due_date, priority=priority)
            TaskRepository(session).add(task)
            return task.id

    def update_task(self, task_id: UUID, **changes: object) -> None:
        allowed = {"title", "description", "project_id", "parent_task_id", "owner_id", "status",
                   "priority", "start_date", "due_date", "progress_mode", "manual_progress"}
        unknown = set(changes) - allowed
        if unknown:
            raise TaskValidationError(f"Unsupported fields: {', '.join(sorted(unknown))}")
        with transaction(self._factory) as session:
            task = self._require_task(session, task_id)
            if "title" in changes:
                title = str(changes["title"]).strip()
                if not title:
                    raise TaskValidationError("Title is required")
                changes["title"] = title
            if "manual_progress" in changes and not 0 <= int(changes["manual_progress"]) <= 100:
                raise TaskValidationError("Progress must be between 0 and 100")
            effective_start = changes.get("start_date", task.start_date)
            effective_due = changes.get("due_date", task.due_date)
            if (effective_start is not None and effective_due is not None
                    and effective_start > effective_due):
                raise TaskValidationError("Start date cannot be later than due date")
            if "parent_task_id" in changes:
                parent_map = dict(session.execute(select(Task.id, Task.parent_task_id)).all())
                ensure_valid_parent(task_id, changes["parent_task_id"], parent_map)  # type: ignore[arg-type]
            if "status" in changes:
                new_status = TaskStatus(changes["status"])
                try:
                    ensure_children_allow_completion(new_status, [child.status for child in task.children])
                except IncompleteChildrenError as error:
                    raise TaskValidationError(str(error)) from error
                task.completed_at = completed_at_for_status(task.status, new_status, task.completed_at,
                                                              now=datetime.now(timezone.utc))
                task.status = new_status
                changes.pop("status")
            for name, value in changes.items():
                setattr(task, name, value)

    def complete_task(self, task_id: UUID, complete: bool = True) -> None:
        self.update_task(task_id, status=TaskStatus.COMPLETE if complete else TaskStatus.NOT_STARTED)

    def cancel_task(self, task_id: UUID) -> None:
        self.update_task(task_id, status=TaskStatus.CANCELLED)

    def delete_task(self, task_id: UUID, *, allow_with_children: bool = False) -> None:
        with transaction(self._factory) as session:
            task = self._require_task(session, task_id)
            if task.children and not allow_with_children:
                raise TaskValidationError("Task has child tasks; confirm recursive deletion")
            TaskRepository(session).delete_hierarchy(task)

    def set_tags(self, task_id: UUID, tag_ids: list[UUID]) -> None:
        with transaction(self._factory) as session:
            task = self._require_task(session, task_id)
            tags = list(session.scalars(select(Tag).where(Tag.id.in_(tag_ids)))) if tag_ids else []
            if len(tags) != len(set(tag_ids)):
                raise TaskValidationError("One or more tags do not exist")
            task.tags = tags

    def add_dependency(self, predecessor_id: UUID, successor_id: UUID) -> UUID:
        with transaction(self._factory) as session:
            predecessor = self._require_task(session, predecessor_id)
            successor = self._require_task(session, successor_id)
            existing = session.scalar(select(Dependency).where(
                Dependency.predecessor_task_id == predecessor_id,
                Dependency.successor_task_id == successor_id,
            ))
            if existing is not None:
                return existing.id
            inactive = {TaskStatus.COMPLETE, TaskStatus.CANCELLED}
            if predecessor.status in inactive or successor.status in inactive:
                raise TaskValidationError(
                    "Completed or cancelled tasks cannot be used for new dependencies.")
            edges = list(session.execute(select(Dependency.predecessor_task_id,
                                                Dependency.successor_task_id)).all())
            try:
                ensure_dependency_is_acyclic(predecessor_id, successor_id, edges)
            except ValueError as error:
                message = ("This dependency would create a circular dependency."
                           if "cycle" in str(error) else "A task cannot depend on itself.")
                raise TaskValidationError(message) from error
            dependency = Dependency(predecessor_task_id=predecessor_id, successor_task_id=successor_id)
            DependencyRepository(session).add(dependency)
            return dependency.id

    def remove_dependency(self, predecessor_id: UUID, successor_id: UUID) -> None:
        """Remove one Finish-to-Start edge, safely doing nothing if it is already absent."""
        with transaction(self._factory) as session:
            dependency = session.scalar(select(Dependency).where(
                Dependency.predecessor_task_id == predecessor_id,
                Dependency.successor_task_id == successor_id,
            ))
            if dependency is not None:
                DependencyRepository(session).delete(dependency)

    def create_owner(self, name: str, **metadata: object) -> UUID:
        clean = name.strip()
        if not clean: raise TaskValidationError("Owner name is required")
        with transaction(self._factory) as session:
            owner = Owner(name=clean, **metadata); OwnerRepository(session).add(owner); return owner.id

    def update_owner(self, owner_id: UUID, **changes: object) -> None:
        with transaction(self._factory) as session:
            owner = OwnerRepository(session).get(owner_id)
            if owner is None: raise TaskValidationError("Owner does not exist")
            for key in {"name", "initials", "avatar_colour", "role", "team", "is_active"} & changes.keys():
                setattr(owner, key, changes[key])

    def create_tag(self, name: str, colour: str | None = None) -> UUID:
        clean = name.strip()
        if not clean: raise TaskValidationError("Tag name is required")
        with transaction(self._factory) as session:
            if session.scalar(select(Tag).where(Tag.name == clean)) is not None:
                raise TaskValidationError("Tag name already exists")
            tag = Tag(name=clean, colour=colour); TagRepository(session).add(tag); return tag.id

    def update_tag(self, tag_id: UUID, *, name: str, colour: str | None = None) -> None:
        clean = name.strip()
        if not clean: raise TaskValidationError("Tag name is required")
        with transaction(self._factory) as session:
            tag = TagRepository(session).get(tag_id)
            if tag is None: raise TaskValidationError("Tag does not exist")
            duplicate = session.scalar(select(Tag).where(Tag.name == clean, Tag.id != tag_id))
            if duplicate: raise TaskValidationError("Tag name already exists")
            tag.name, tag.colour = clean, colour

    @staticmethod
    def _require_task(session: Session, task_id: UUID) -> Task:
        task = TaskRepository(session).get(task_id)
        if task is None: raise TaskValidationError("Task does not exist")
        return task
