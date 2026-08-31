"""Create the M1 persistence schema.

Revision ID: 0001
Revises: None
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owners",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("name", sa.String(), nullable=False),
        sa.Column("initials", sa.String()), sa.Column("avatar_colour", sa.String()),
        sa.Column("role", sa.String()), sa.Column("team", sa.String()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.Enum("PLANNED", "ACTIVE", "ON_HOLD", "COMPLETE", "ARCHIVED", name="projectstatus", native_enum=False), nullable=False),
        sa.Column("colour", sa.String()), sa.Column("start_date", sa.Date()), sa.Column("due_date", sa.Date()),
        sa.Column("progress_mode", sa.Enum("AUTOMATIC", "MANUAL", name="progressmode", native_enum=False), nullable=False),
        sa.Column("manual_progress", sa.Integer(), nullable=False), sa.Column("is_pinned", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("manual_progress BETWEEN 0 AND 100", name="ck_projects_manual_progress"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("name", sa.String(), nullable=False),
        sa.Column("colour", sa.String()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("name"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("project_id", sa.Uuid()), sa.Column("parent_task_id", sa.Uuid()),
        sa.Column("title", sa.String(), nullable=False), sa.Column("description", sa.Text()), sa.Column("owner_id", sa.Uuid()),
        sa.Column("status", sa.Enum("NOT_STARTED", "IN_PROGRESS", "BLOCKED", "WAITING", "COMPLETE", "CANCELLED", name="taskstatus", native_enum=False), nullable=False),
        sa.Column("priority", sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="taskpriority", native_enum=False), nullable=False),
        sa.Column("start_date", sa.Date()), sa.Column("due_date", sa.Date()),
        sa.Column("progress_mode", sa.Enum("AUTOMATIC", "MANUAL", name="progressmode", native_enum=False), nullable=False),
        sa.Column("manual_progress", sa.Integer(), nullable=False), sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_milestone", sa.Boolean(), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("manual_progress BETWEEN 0 AND 100", name="ck_tasks_manual_progress"),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tasks_owner_id"), "tasks", ["owner_id"])
    op.create_index(op.f("ix_tasks_parent_task_id"), "tasks", ["parent_task_id"])
    op.create_index(op.f("ix_tasks_project_id"), "tasks", ["project_id"])
    op.create_table(
        "dependencies",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("predecessor_task_id", sa.Uuid(), nullable=False),
        sa.Column("successor_task_id", sa.Uuid(), nullable=False),
        sa.Column("dependency_type", sa.Enum("FINISH_TO_START", name="dependencytype", native_enum=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("predecessor_task_id != successor_task_id", name="ck_dependencies_distinct_tasks"),
        sa.ForeignKeyConstraint(["predecessor_task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["successor_task_id"], ["tasks.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("predecessor_task_id", "successor_task_id", name="uq_dependencies_tasks"),
    )
    op.create_index(op.f("ix_dependencies_predecessor_task_id"), "dependencies", ["predecessor_task_id"])
    op.create_index(op.f("ix_dependencies_successor_task_id"), "dependencies", ["successor_task_id"])
    op.create_table(
        "task_tags", sa.Column("task_id", sa.Uuid(), nullable=False), sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("task_id", "tag_id"),
    )


def downgrade() -> None:
    op.drop_table("task_tags")
    op.drop_index(op.f("ix_dependencies_successor_task_id"), table_name="dependencies")
    op.drop_index(op.f("ix_dependencies_predecessor_task_id"), table_name="dependencies")
    op.drop_table("dependencies")
    op.drop_index(op.f("ix_tasks_project_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_parent_task_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_owner_id"), table_name="tasks")
    op.drop_table("tasks")
    op.drop_table("tags")
    op.drop_table("projects")
    op.drop_table("owners")
