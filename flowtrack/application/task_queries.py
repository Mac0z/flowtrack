"""Efficient, UI-neutral read models for Dashboard and My Tasks."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from uuid import UUID
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload, sessionmaker
from flowtrack.domain.enums import ProjectStatus, TaskPriority, TaskStatus
from flowtrack.domain.services import (
    calculate_project_progress,
    calculate_task_automatic_progress,
    calculate_task_progress,
    is_overdue,
)
from flowtrack.persistence.models import Dependency, Owner, Project, Tag, Task

DUE_SOON_DAYS = 7

@dataclass(frozen=True, slots=True)
class TaskFilters:
    statuses: frozenset[TaskStatus] = field(default_factory=frozenset)
    priorities: frozenset[TaskPriority] = field(default_factory=frozenset)
    project_id: UUID | None = None
    owner_id: UUID | None = None
    tag_ids: frozenset[UUID] = field(default_factory=frozenset)
    due_from: date | None = None
    due_to: date | None = None

@dataclass(frozen=True, slots=True)
class TaskRow:
    id: UUID; title: str; description: str; status: TaskStatus; priority: TaskPriority
    project_id: UUID | None; project_name: str | None; owner_id: UUID | None; owner_name: str | None
    due_date: date | None; start_date: date | None; progress: float; sort_order: int
    tags: tuple[tuple[UUID, str], ...]; overdue: bool
    parent_task_id: UUID | None; hierarchy_depth: int

@dataclass(frozen=True, slots=True)
class DashboardData:
    active_projects: int; in_progress: int; completed: int; overdue: int
    due_this_week: tuple[TaskRow, ...]; projects: tuple[tuple[UUID, str, float, int, date | None], ...]
    pinned_projects: tuple[tuple[UUID, str], ...]

class TaskQueryService:
    """Produces bounded eager-loaded read models without leaking ORM objects."""
    def __init__(self, factory: sessionmaker[Session]) -> None: self._factory = factory

    def my_tasks(self, *, search: str = "", filters: TaskFilters | None = None,
                 today: date | None = None, limit: int = 1000) -> list[TaskRow]:
        today, filters = today or date.today(), filters or TaskFilters()
        with self._factory() as session:
            stmt = select(Task).options(selectinload(Task.tags), selectinload(Task.children),
                         selectinload(Task.project), selectinload(Task.owner))
            if search.strip():
                term = f"%{search.strip().casefold()}%"
                stmt = stmt.where(or_(func.lower(Task.title).like(term), func.lower(Task.description).like(term)))
            if filters.statuses: stmt = stmt.where(Task.status.in_(filters.statuses))
            if filters.priorities: stmt = stmt.where(Task.priority.in_(filters.priorities))
            if filters.project_id: stmt = stmt.where(Task.project_id == filters.project_id)
            if filters.owner_id: stmt = stmt.where(Task.owner_id == filters.owner_id)
            if filters.tag_ids: stmt = stmt.where(Task.tags.any(Tag.id.in_(filters.tag_ids)))
            if filters.due_from: stmt = stmt.where(Task.due_date >= filters.due_from)
            if filters.due_to: stmt = stmt.where(Task.due_date <= filters.due_to)
            tasks = list(session.scalars(stmt.limit(limit)).unique())
            parent_by_id = dict(session.execute(select(Task.id, Task.parent_task_id)).all())
            rows = [self._row(task, today, self._hierarchy_depth(task.id, parent_by_id)) for task in tasks]
        priority = {TaskPriority.CRITICAL: 0, TaskPriority.HIGH: 1, TaskPriority.MEDIUM: 2, TaskPriority.LOW: 3}
        def key(row: TaskRow) -> tuple[object, ...]:
            active = row.status not in (TaskStatus.COMPLETE, TaskStatus.CANCELLED)
            due_soon = active and row.due_date is not None and today <= row.due_date <= today + timedelta(days=DUE_SOON_DAYS)
            return (not row.overdue, not due_soon, priority[row.priority], row.sort_order, row.id.hex)
        return self._hierarchy_order(rows, parent_by_id, key)

    @staticmethod
    def _hierarchy_depth(task_id: UUID, parent_by_id: dict[UUID, UUID | None]) -> int:
        depth = 0
        seen = {task_id}
        parent_id = parent_by_id.get(task_id)
        while parent_id is not None and parent_id not in seen:
            depth += 1
            seen.add(parent_id)
            parent_id = parent_by_id.get(parent_id)
        return depth

    @staticmethod
    def _hierarchy_order(
        rows: list[TaskRow],
        parent_by_id: dict[UUID, UUID | None],
        key,
    ) -> list[TaskRow]:
        """Keep visible descendant subtrees together while retaining task sort intent."""
        visible = {row.id: row for row in rows}
        children: dict[UUID, list[TaskRow]] = {}
        roots: list[TaskRow] = []
        for row in rows:
            parent_id = parent_by_id.get(row.id)
            seen = {row.id}
            while parent_id is not None and parent_id not in visible and parent_id not in seen:
                seen.add(parent_id)
                parent_id = parent_by_id.get(parent_id)
            if parent_id in visible:
                children.setdefault(parent_id, []).append(row)
            else:
                roots.append(row)

        ordered: list[TaskRow] = []
        def append_subtree(row: TaskRow) -> None:
            ordered.append(row)
            for child in sorted(children.get(row.id, ()), key=key):
                append_subtree(child)

        for root in sorted(roots, key=key):
            append_subtree(root)
        return ordered

    def task_detail(self, task_id: UUID) -> dict[str, object] | None:
        with self._factory() as session:
            task = session.scalar(select(Task).where(Task.id == task_id).options(
                selectinload(Task.tags), selectinload(Task.children), selectinload(Task.owner), selectinload(Task.project)))
            if task is None: return None
            predecessors = list(session.scalars(select(Task).join(Dependency, Task.id == Dependency.predecessor_task_id)
                .where(Dependency.successor_task_id == task_id)))
            return {"id": task.id, "title": task.title, "description": task.description or "", "status": task.status,
                    "priority": task.priority, "owner_id": task.owner_id, "project_id": task.project_id,
                    "start_date": task.start_date, "due_date": task.due_date, "progress": calculate_task_progress(task),
                    "progress_mode": task.progress_mode, "manual_progress": task.manual_progress,
                    "automatic_progress": calculate_task_automatic_progress(task),
                    "tags": tuple((t.id, t.name) for t in task.tags),
                    "children": tuple((c.id, c.title, c.status) for c in task.children),
                    "dependencies": tuple((p.id, p.title) for p in predecessors)}

    def dashboard(self, *, today: date | None = None) -> DashboardData:
        today = today or date.today()
        rows = self.my_tasks(today=today)
        week_end = today + timedelta(days=6 - today.weekday())
        due_week = tuple(r for r in rows if r.due_date is not None and today <= r.due_date <= week_end
                         and r.status not in (TaskStatus.COMPLETE, TaskStatus.CANCELLED))
        with self._factory() as session:
            projects = list(session.scalars(select(Project).options(selectinload(Project.tasks).selectinload(Task.children))))
            overview = tuple((p.id, p.name, calculate_project_progress(p), len(p.tasks), p.due_date) for p in projects
                             if p.status is not ProjectStatus.ARCHIVED)
            pinned = tuple((p.id, p.name) for p in projects if p.is_pinned and p.status is not ProjectStatus.ARCHIVED)
        return DashboardData(sum(p.status is ProjectStatus.ACTIVE for p in projects),
            sum(r.status is TaskStatus.IN_PROGRESS for r in rows), sum(r.status is TaskStatus.COMPLETE for r in rows),
            sum(r.overdue for r in rows), due_week, overview, pinned)

    @staticmethod
    def _row(task: Task, today: date, hierarchy_depth: int = 0) -> TaskRow:
        return TaskRow(task.id, task.title, task.description or "", task.status, task.priority,
            task.project_id, task.project.name if task.project else None, task.owner_id,
            task.owner.name if task.owner else None, task.due_date, task.start_date,
            calculate_task_progress(task), task.sort_order, tuple((t.id, t.name) for t in task.tags),
            is_overdue(due_date=task.due_date, status=task.status, today=today),
            task.parent_task_id, hierarchy_depth)

    def owners(self, active_only: bool = False) -> list[tuple[UUID, str, bool]]:
        with self._factory() as s:
            stmt = select(Owner).order_by(Owner.name)
            if active_only: stmt = stmt.where(Owner.is_active)
            return [(o.id, o.name, o.is_active) for o in s.scalars(stmt)]
    def tags(self) -> list[tuple[UUID, str]]:
        with self._factory() as s: return [(t.id, t.name) for t in s.scalars(select(Tag).order_by(Tag.name))]
    def projects(self) -> list[tuple[UUID, str]]:
        with self._factory() as s: return [(p.id, p.name) for p in s.scalars(select(Project).where(Project.status != ProjectStatus.ARCHIVED).order_by(Project.name))]
