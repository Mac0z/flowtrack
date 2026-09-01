"""Transactional commands and UI-neutral read models for M5 projects."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from flowtrack.domain.enums import ProgressMode, ProjectStatus, TaskStatus
from flowtrack.domain.services import calculate_project_progress, is_overdue
from flowtrack.persistence.database import transaction
from flowtrack.persistence.models import Project, Task
from flowtrack.persistence.repositories import ProjectRepository
from flowtrack.application.task_queries import TaskFilters, TaskQueryService, TaskRow


class ProjectValidationError(ValueError):
    """A user-correctable project input error."""


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    id: UUID
    name: str
    description: str
    status: ProjectStatus
    colour: str | None
    start_date: date | None
    due_date: date | None
    progress_mode: ProgressMode
    manual_progress: int
    is_pinned: bool
    progress: float
    task_count: int
    completed_count: int
    overdue_count: int
    blocked_count: int


class ProjectService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def create_project(self, name: str, **values: object) -> UUID:
        clean = name.strip()
        if not clean:
            raise ProjectValidationError("Name is required")
        allowed = {"description", "status", "colour", "start_date", "due_date",
                   "progress_mode", "manual_progress", "is_pinned"}
        self._validate(values, allowed)
        with transaction(self._factory) as session:
            project = Project(name=clean, **values)
            ProjectRepository(session).add(project)
            return project.id

    def update_project(self, project_id: UUID, **values: object) -> None:
        allowed = {"name", "description", "status", "colour", "start_date", "due_date",
                   "progress_mode", "manual_progress", "is_pinned"}
        self._validate(values, allowed)
        if "name" in values:
            values["name"] = str(values["name"]).strip()
            if not values["name"]:
                raise ProjectValidationError("Name is required")
        with transaction(self._factory) as session:
            project = ProjectRepository(session).get(project_id)
            if project is None:
                raise ProjectValidationError("Project does not exist")
            start = values.get("start_date", project.start_date)
            due = values.get("due_date", project.due_date)
            if start and due and start > due:  # type: ignore[operator]
                raise ProjectValidationError("Due date cannot be before start date")
            for key, value in values.items():
                setattr(project, key, value)

    def set_pinned(self, project_id: UUID, pinned: bool) -> None:
        self.update_project(project_id, is_pinned=pinned)

    def archive_project(self, project_id: UUID) -> None:
        self.update_project(project_id, status=ProjectStatus.ARCHIVED)

    def unarchive_project(self, project_id: UUID, *, status: ProjectStatus = ProjectStatus.PLANNED) -> None:
        if status is ProjectStatus.ARCHIVED:
            raise ProjectValidationError("Restored status cannot be Archived")
        self.update_project(project_id, status=status)

    @staticmethod
    def _validate(values: dict[str, object], allowed: set[str]) -> None:
        unknown = set(values) - allowed
        if unknown:
            raise ProjectValidationError(f"Unsupported fields: {', '.join(sorted(unknown))}")
        if "manual_progress" in values and not 0 <= int(values["manual_progress"]) <= 100:
            raise ProjectValidationError("Progress must be between 0 and 100")
        if values.get("start_date") and values.get("due_date") and values["start_date"] > values["due_date"]:  # type: ignore[operator]
            raise ProjectValidationError("Due date cannot be before start date")


class ProjectQueryService:
    _STATUS_ORDER = {ProjectStatus.ACTIVE: 0, ProjectStatus.PLANNED: 1,
                     ProjectStatus.ON_HOLD: 2, ProjectStatus.COMPLETE: 3,
                     ProjectStatus.ARCHIVED: 4}

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def list_projects(self, *, include_archived: bool = False, today: date | None = None) -> list[ProjectSummary]:
        with self._factory() as session:
            stmt = select(Project).options(selectinload(Project.tasks).selectinload(Task.children))
            if not include_archived:
                stmt = stmt.where(Project.status != ProjectStatus.ARCHIVED)
            projects = list(session.scalars(stmt).unique())
            result = [self._summary(project, today or date.today()) for project in projects]
        far_future = date.max
        return sorted(result, key=lambda p: (not p.is_pinned, self._STATUS_ORDER[p.status],
                                              p.due_date or far_future, p.name.casefold(), str(p.id)))

    def project_detail(self, project_id: UUID, *, today: date | None = None) -> ProjectSummary | None:
        with self._factory() as session:
            project = session.scalar(select(Project).where(Project.id == project_id).options(
                selectinload(Project.tasks).selectinload(Task.children)))
            return None if project is None else self._summary(project, today or date.today())

    def project_tasks(self, project_id: UUID, *, today: date | None = None) -> list[TaskRow]:
        rows = TaskQueryService(self._factory).my_tasks(
            filters=TaskFilters(project_id=project_id),
            today=today, limit=25000)
        sibling_key = lambda row: (row.sort_order, row.title.casefold(), str(row.id))
        parents = {row.id: row.parent_task_id for row in rows}
        return TaskQueryService._hierarchy_order(rows, parents, sibling_key)

    def pinned_projects(self) -> list[ProjectSummary]:
        return [p for p in self.list_projects() if p.is_pinned]

    @staticmethod
    def _summary(project: Project, today: date) -> ProjectSummary:
        tasks = project.tasks
        return ProjectSummary(project.id, project.name, project.description or "", project.status,
            project.colour, project.start_date, project.due_date, project.progress_mode,
            project.manual_progress, project.is_pinned, calculate_project_progress(project), len(tasks),
            sum(t.status is TaskStatus.COMPLETE for t in tasks),
            sum(is_overdue(due_date=t.due_date, status=t.status, today=today) for t in tasks),
            sum(t.status is TaskStatus.BLOCKED for t in tasks))
