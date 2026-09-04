"""Discovery and validation of read-only resources bundled with FlowTrack."""

from importlib.resources import files
from pathlib import Path


def migration_directory() -> Path:
    """Return Alembic's filesystem migration directory in source or frozen runs."""
    location = Path(str(files("flowtrack.persistence.migrations")))
    required = (location / "env.py", location / "script.py.mako", location / "versions")
    if not all(item.exists() for item in required):
        raise RuntimeError("FlowTrack migration resources are incomplete")
    return location
