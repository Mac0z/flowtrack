"""Database engine, migration, and transaction lifecycle helpers."""

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from flowtrack.infrastructure.resources import migration_directory

logger = logging.getLogger(__name__)


class JournalConfigurationError(RuntimeError):
    """SQLite could not safely enter FlowTrack's conservative journal mode."""


def configure_sqlite_journal(path: Path) -> None:
    """Safely select DELETE journalling at a boundary with no app connections."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    try:
        current = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        logger.info("Detected SQLite journal mode for %s: %s", path, current)
        if current == "wal":
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint is None or int(checkpoint[0]) != 0:
                raise JournalConfigurationError(
                    "FlowTrack could not safely checkpoint the existing WAL database."
                )
        selected = str(connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]).lower()
        if selected != "delete":
            raise JournalConfigurationError(
                f"SQLite retained unsupported journal mode {selected!r}."
            )
        connection.execute("PRAGMA synchronous=FULL")
        logger.info("SQLite journal configuration selected DELETE with synchronous FULL")
    except sqlite3.Error as error:
        raise JournalConfigurationError(
            "FlowTrack could not safely configure SQLite journalling."
        ) from error
    finally:
        connection.close()


def database_url(path: Path) -> str:
    """Build a portable SQLAlchemy SQLite URL from a filesystem path."""
    return f"sqlite:///{path.resolve().as_posix()}"


def create_database_engine(path: Path, *, echo: bool = False, read_only: bool = False) -> Engine:
    """Create an engine for a FlowTrack database without creating its schema."""
    if read_only:
        # SQLite URI mode enforces read-only access below the application layer.
        url = f"sqlite:///file:{path.resolve().as_posix()}?mode=ro&uri=true"
    else:
        configure_sqlite_journal(path)
        url = database_url(path)
    engine = create_engine(url, echo=echo)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.close()

    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create sessions that retain values after a successful commit."""
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def transaction(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit all work atomically, or roll it back if an exception escapes."""
    with factory() as session, session.begin():
        yield session


def migration_config(url: str | None = None) -> Config:
    """Return an Alembic configuration rooted in the installed package."""
    config = Config()
    config.set_main_option("script_location", str(migration_directory()))
    if url is not None:
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def migrate_database(path: Path, revision: str = "head") -> None:
    """Create or upgrade a database to a versioned schema revision."""
    path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(migration_config(database_url(path)), revision)


def migration_status(path: Path) -> tuple[str | None, str]:
    """Return the database revision (if any) and configured Alembic head."""
    config = migration_config(database_url(path))
    head = ScriptDirectory.from_config(config).get_current_head()
    if head is None:
        raise RuntimeError("FlowTrack migration history has no head revision")
    if not path.is_file() or path.stat().st_size == 0:
        return None, head
    engine = create_database_engine(path, read_only=True)
    try:
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()
    return current, head


def migration_required(path: Path) -> bool:
    current, head = migration_status(path)
    return path.is_file() and path.stat().st_size > 0 and current != head
