"""Database engine, migration, and transaction lifecycle helpers."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def database_url(path: Path) -> str:
    """Build a portable SQLAlchemy SQLite URL from a filesystem path."""
    return f"sqlite:///{path.resolve().as_posix()}"


def create_database_engine(path: Path, *, echo: bool = False, read_only: bool = False) -> Engine:
    """Create an engine for a FlowTrack database without creating its schema."""
    if read_only:
        # SQLite URI mode enforces read-only access below the application layer.
        url = f"sqlite:///file:{path.resolve().as_posix()}?mode=ro&uri=true"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        url = database_url(path)
    engine = create_engine(url, echo=echo)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
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
    migrations = Path(__file__).parent / "migrations"
    config = Config()
    config.set_main_option("script_location", str(migrations))
    if url is not None:
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def migrate_database(path: Path, revision: str = "head") -> None:
    """Create or upgrade a database to a versioned schema revision."""
    path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(migration_config(database_url(path)), revision)
