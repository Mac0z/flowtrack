"""Private validation used by native packaged-build jobs."""

import tempfile
from pathlib import Path


def run_packaging_smoke() -> None:
    """Exercise bundled imports, resources, migrations, and SQLite in isolation."""
    import alembic
    import sqlalchemy
    from PySide6.QtCore import qVersion

    from flowtrack import __version__
    from flowtrack.infrastructure.backup import check_integrity
    from flowtrack.infrastructure.resources import migration_directory
    from flowtrack.persistence.database import migrate_database, migration_status

    if not __version__ or not qVersion() or not alembic.__version__ or not sqlalchemy.__version__:
        raise RuntimeError("Required packaged runtime version information is unavailable")
    migration_directory()
    with tempfile.TemporaryDirectory(prefix="flowtrack-packaging-smoke-") as temporary:
        database = Path(temporary) / "dataset" / "flowtrack.db"
        migrate_database(database)
        current, head = migration_status(database)
        if current != head or not check_integrity(database).ok:
            raise RuntimeError("Packaged database migration smoke check failed")
