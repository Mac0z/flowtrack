"""Small session-scoped repository for mapped FlowTrack entities."""

from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from flowtrack.persistence.models import Base, Dependency, Owner, Project, Tag, Task

Model = TypeVar("Model", bound=Base)


class Repository(Generic[Model]):
    """Provide CRUD operations while leaving transaction ownership to callers."""

    def __init__(self, session: Session, model: type[Model]) -> None:
        self._session = session
        self._model = model

    def add(self, entity: Model) -> Model:
        self._session.add(entity)
        self._session.flush()
        return entity

    def get(self, entity_id: UUID) -> Model | None:
        return self._session.get(self._model, entity_id)

    def list(self) -> list[Model]:
        return list(self._session.scalars(select(self._model)))

    def delete(self, entity: Model) -> None:
        self._session.delete(entity)
        self._session.flush()


class ProjectRepository(Repository[Project]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Project)


class TaskRepository(Repository[Task]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Task)

    def list_children(self, parent_task_id: UUID | None) -> list[Task]:
        """Return one hierarchy level in stable sibling order."""
        statement = (
            select(Task)
            .where(Task.parent_task_id == parent_task_id)
            .order_by(Task.sort_order, Task.created_at, Task.id)
        )
        return list(self._session.scalars(statement))


class OwnerRepository(Repository[Owner]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Owner)


class TagRepository(Repository[Tag]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Tag)


class DependencyRepository(Repository[Dependency]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Dependency)
