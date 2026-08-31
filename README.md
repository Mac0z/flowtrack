# FlowTrack

FlowTrack is a local-first, cross-platform desktop task and project manager. This
repository contains the M0 application skeleton and the **M1 persistence
foundation**: a versioned SQLite schema, SQLAlchemy 2.x mappings, transaction
helpers, and session-scoped repositories. Task business rules and finished UI
workflows belong to later milestones and are not implemented yet.

## Development setup

Use Python 3.12. FlowTrack does not support other Python feature releases. The
Qt API baseline is pinned to PySide6 6.7.3.

```console
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
python -m flowtrack
```

FlowTrack writes rotating diagnostic logs beneath the operating system's normal
per-user application-data location. Persistence clients initialize a chosen
database path with `flowtrack.persistence.database.migrate_database`; selecting
a portable dataset location remains a later application workflow.

## Persistence development

M1 uses SQLAlchemy 2.x and Alembic. Schema changes are represented by revisions
in `flowtrack/persistence/migrations/`; never replace migration history with a
direct `Base.metadata.create_all()` call. Repositories participate in a caller-
owned transaction:

```python
engine = create_database_engine(database_path)
factory = session_factory(engine)
with transaction(factory) as session:
    Repository(session, Project).add(Project(name="Example"))
```

SQLite foreign-key enforcement is enabled for every application engine. No WAL
journal mode is selected by M1; cloud-folder durability and locking decisions
remain explicitly deferred to M8.

## Compatibility assumptions

- macOS 11 Big Sur or newer is supported on Intel and Apple Silicon.
- Windows 10 and 11 x86-64 are supported.
- Release artifacts must be built and smoke-tested on their target OS; they are
  not cross-built.
- Paths are represented with `pathlib.Path`. macOS uses
  `~/Library/Application Support/FlowTrack`; Windows uses `LOCALAPPDATA` (with
  the user's home as a safe fallback). No OneDrive location is assumed.
- Linux is supported only as a development/CI host and follows XDG conventions;
  it is not a product release target.
- Python 3.12 is the sole supported Python feature release, with PySide6 6.7.3
  pinned as the required Qt API baseline.
