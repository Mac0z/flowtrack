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

## Local backups and restore

FlowTrack keeps all backups locally in the selected dataset's `backups/`
directory. Managed files use UTC names such as
`flowtrack-20260903-141500-daily.db`; the other types are `manual`, `migration`,
and `pre-restore`. Backups are complete standalone SQLite databases created
through SQLite's native backup API and are integrity-checked before adoption.

During a writable startup, FlowTrack creates at most one daily backup per UTC
calendar day when the database is newer than the newest managed backup. This is
a conservative filesystem-modification-time policy that avoids adding tracking
data to the user's schema. The newest 30 daily backups are retained; manual,
migration, and pre-restore backups are never removed by automatic retention.
An existing database is backed up before any required schema migration.

Settings provides **Backup Now** and a compact list of validated backups. A
restore validates its source, creates and validates a pre-restore safety backup,
closes active database connections, atomically adopts and revalidates the
selected database, and then closes FlowTrack so that the next launch starts with
fresh sessions. Mutating backup operations are unavailable in read-only mode.

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

## M4 task execution ordering

M4 opens a migrated SQLite database named `flowtrack.db` in the platform's
conventional application-data directory. Selectable data locations and
associated data-safety workflows remain deliberately deferred to M8.

My Tasks orders unfinished overdue work first, then work due within the next
**seven calendar days** (inclusive), then Critical/High/Medium/Low priority,
and finally the persisted sibling `sort_order` and stable UUID. Overdue checks
use the computer's local calendar date. Search matches task titles and
descriptions without case sensitivity; filter preferences are stored in Qt
settings while task data remains in SQLite.

## Gantt dependency creation

The Gantt supports direct Finish-to-Start dependency creation by dragging the
hover handle at the right of a dated, active task onto another visible task
row. Complete and Cancelled tasks cannot be sources or targets, and the Task
Inspector remains the dependency editor for undated source tasks. Horizontal
auto-scroll during a dependency drag is intentionally deferred as future
polish; users can scroll the timeline before starting a drag.
