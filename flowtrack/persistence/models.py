"""SQLAlchemy mappings for the M1 FlowTrack schema."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from flowtrack.domain.enums import DependencyType, ProgressMode, ProjectStatus, TaskPriority, TaskStatus


def utc_now() -> datetime:
    """Return an aware UTC timestamp for audit columns."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint("manual_progress BETWEEN 0 AND 100", name="ck_projects_manual_progress"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus, native_enum=False), default=ProjectStatus.PLANNED, nullable=False)
    colour: Mapped[str | None] = mapped_column(String)
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    progress_mode: Mapped[ProgressMode] = mapped_column(Enum(ProgressMode, native_enum=False), default=ProgressMode.AUTOMATIC, nullable=False)
    manual_progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tasks: Mapped[list[Task]] = relationship(back_populates="project")


class Owner(TimestampMixin, Base):
    __tablename__ = "owners"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    initials: Mapped[str | None] = mapped_column(String)
    avatar_colour: Mapped[str | None] = mapped_column(String)
    role: Mapped[str | None] = mapped_column(String)
    team: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tasks: Mapped[list[Task]] = relationship(back_populates="owner")


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (CheckConstraint("manual_progress BETWEEN 0 AND 100", name="ck_tasks_manual_progress"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    parent_task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("owners.id", ondelete="SET NULL"), index=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus, native_enum=False), default=TaskStatus.NOT_STARTED, nullable=False)
    priority: Mapped[TaskPriority] = mapped_column(Enum(TaskPriority, native_enum=False), default=TaskPriority.MEDIUM, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    progress_mode: Mapped[ProgressMode] = mapped_column(Enum(ProgressMode, native_enum=False), default=ProgressMode.AUTOMATIC, nullable=False)
    manual_progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project | None] = relationship(back_populates="tasks")
    owner: Mapped[Owner | None] = relationship(back_populates="tasks")
    parent: Mapped[Task | None] = relationship(back_populates="children", remote_side="Task.id")
    children: Mapped[list[Task]] = relationship(back_populates="parent", passive_deletes=True)
    tags: Mapped[list[Tag]] = relationship(secondary="task_tags", back_populates="tasks")


class Tag(TimestampMixin, Base):
    __tablename__ = "tags"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    colour: Mapped[str | None] = mapped_column(String)
    tasks: Mapped[list[Task]] = relationship(secondary="task_tags", back_populates="tags")


class TaskTag(Base):
    __tablename__ = "task_tags"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[UUID] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class Dependency(TimestampMixin, Base):
    __tablename__ = "dependencies"
    __table_args__ = (
        UniqueConstraint("predecessor_task_id", "successor_task_id", name="uq_dependencies_tasks"),
        CheckConstraint("predecessor_task_id != successor_task_id", name="ck_dependencies_distinct_tasks"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    predecessor_task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    successor_task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    dependency_type: Mapped[DependencyType] = mapped_column(Enum(DependencyType, native_enum=False), default=DependencyType.FINISH_TO_START, nullable=False)
