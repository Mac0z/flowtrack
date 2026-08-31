from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from flowtrack.persistence.database import create_database_engine, migrate_database, migration_config, session_factory, transaction
from flowtrack.persistence.models import Dependency, Owner, Project, Tag, Task
from flowtrack.persistence.repositories import Repository


def test_empty_database_migrates_to_head(tmp_path) -> None:
    database_path = tmp_path / "dataset" / "flowtrack.db"
    migrate_database(database_path)

    engine = create_database_engine(database_path)
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version", "dependencies", "owners", "projects", "tags", "task_tags", "tasks"
    }
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Project.__table__)) == 0
    engine.dispose()


def test_initial_migration_can_downgrade_and_upgrade(tmp_path) -> None:
    database_path = tmp_path / "flowtrack.db"
    migrate_database(database_path)
    config = migration_config(f"sqlite:///{database_path.as_posix()}")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_database_engine(database_path)
    assert "tasks" in inspect(engine).get_table_names()
    engine.dispose()


def test_repositories_persist_m1_entities_and_relationships(tmp_path) -> None:
    database_path = tmp_path / "flowtrack.db"
    migrate_database(database_path)
    engine = create_database_engine(database_path)
    factory = session_factory(engine)

    with transaction(factory) as session:
        project = Repository(session, Project).add(Project(name="Launch"))
        owner = Repository(session, Owner).add(Owner(name="Alex"))
        tag = Repository(session, Tag).add(Tag(name="Important"))
        parent = Repository(session, Task).add(Task(title="Plan", project=project, owner=owner))
        child = Repository(session, Task).add(Task(title="Execute", project=project, parent=parent))
        child.tags.append(tag)
        dependency = Repository(session, Dependency).add(
            Dependency(predecessor_task_id=parent.id, successor_task_id=child.id)
        )
        identifiers = project.id, owner.id, tag.id, parent.id, child.id, dependency.id

    with transaction(factory) as session:
        project_id, owner_id, tag_id, parent_id, child_id, dependency_id = identifiers
        assert Repository(session, Project).get(project_id).name == "Launch"  # type: ignore[union-attr]
        assert Repository(session, Owner).get(owner_id).name == "Alex"  # type: ignore[union-attr]
        stored_child = Repository(session, Task).get(child_id)
        assert stored_child is not None
        assert stored_child.parent_task_id == parent_id
        assert stored_child.tags[0].id == tag_id
        stored_child.title = "Deliver"
        Repository(session, Dependency).delete(Repository(session, Dependency).get(dependency_id))  # type: ignore[arg-type]

    with transaction(factory) as session:
        assert Repository(session, Task).get(child_id).title == "Deliver"  # type: ignore[union-attr]
        assert Repository(session, Dependency).list() == []
    engine.dispose()


def test_transaction_rolls_back_all_writes(tmp_path) -> None:
    database_path = tmp_path / "flowtrack.db"
    migrate_database(database_path)
    engine = create_database_engine(database_path)
    factory = session_factory(engine)

    with pytest.raises(RuntimeError):
        with transaction(factory) as session:
            Repository(session, Project).add(Project(name="Not committed"))
            raise RuntimeError("abort")

    with transaction(factory) as session:
        assert Repository(session, Project).list() == []
    engine.dispose()


def test_schema_constraints_and_foreign_keys_are_enforced(tmp_path) -> None:
    database_path = tmp_path / "flowtrack.db"
    migrate_database(database_path)
    engine = create_database_engine(database_path)
    factory = session_factory(engine)

    with pytest.raises(IntegrityError), transaction(factory) as session:
        Repository(session, Project).add(Project(name="Invalid", manual_progress=101))
    with pytest.raises(IntegrityError), transaction(factory) as session:
        Repository(session, Task).add(Task(title="Orphan", project_id=uuid4()))
    engine.dispose()
