"""Repository interfaces for M1 persistence operations."""

from flowtrack.persistence.repositories.base import (
    DependencyRepository,
    OwnerRepository,
    ProjectRepository,
    Repository,
    TagRepository,
    TaskRepository,
)

__all__ = [
    "DependencyRepository",
    "OwnerRepository",
    "ProjectRepository",
    "Repository",
    "TagRepository",
    "TaskRepository",
]
