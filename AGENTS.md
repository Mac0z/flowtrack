# AGENTS.md

## Purpose

This repository contains **FlowTrack**, a cross-platform desktop task and project management application for macOS and Windows.

`SPEC.md` is the product and engineering source of truth.

Before making any substantive change, read `SPEC.md` and this file.

---

## Working Principles

1. **Follow the specification**
   - Do not silently change product behaviour, architecture, data semantics, or platform support.
   - If a requirement is ambiguous, state the ambiguity and choose the smallest reasonable implementation consistent with `SPEC.md`.
   - Do not invent major features that are not requested.

2. **Work only within the requested scope**
   - Implement only the milestone, feature, bug, or refactor requested in the current task.
   - Do not continue into later milestones unless explicitly asked.
   - Avoid unrelated cleanup unless it is required to complete the requested work safely.

3. **Keep the application cross-platform**
   - macOS and Windows are equal first-class targets.
   - Use `pathlib` for filesystem paths.
   - Prefer Qt and Python cross-platform APIs.
   - Isolate unavoidable OS-specific behaviour in `flowtrack/infrastructure/`.
   - Never hard-code Windows or macOS paths.

4. **Protect user data**
   - Treat database integrity as a critical requirement.
   - Use transactions for multi-record writes.
   - Never silently discard, overwrite, merge, or repair user databases.
   - Database migrations must be versioned and tested.
   - Backup/recovery logic must fail safely.
   - Do not weaken the local lock or dataset session-lease protections described in `SPEC.md`.

5. **Maintain clean architecture**
   - UI code must not execute raw SQL.
   - Business rules belong outside Qt view/widget classes.
   - Persistence behaviour belongs in repositories / persistence services.
   - Platform-specific behaviour belongs behind infrastructure helpers.
   - Avoid large monolithic classes and unnecessary abstractions.

6. **Keep dependencies minimal**
   - Do not add a new third-party dependency unless it materially improves the implementation.
   - Prefer Python standard library, Qt/PySide6, SQLAlchemy, Alembic, and pytest where suitable.
   - Explain any significant new dependency in the change summary.

---

## Target Repository Structure

Prefer the following structure unless `SPEC.md` is deliberately updated:

```text
flowtrack/
  __init__.py
  __main__.py
  app.py

  ui/
    windows/
    views/
    widgets/
    dialogs/
    theme/

  domain/
    models.py
    enums.py
    services/

  persistence/
    database.py
    repositories/
    migrations/

  application/
    commands/
    queries/

  infrastructure/
    locking.py
    backup.py
    paths.py
    platform.py
    logging.py

tests/
docs/
SPEC.md
AGENTS.md
README.md
```

---

## Coding Standards

- Target Python 3.12 only.
- Use type hints for public functions, methods, and important internal interfaces.
- Prefer small, explicit functions over clever or highly dynamic code.
- Use descriptive names.
- Keep domain logic independent of Qt wherever practical.
- Avoid global mutable state.
- Use UUIDs for domain identifiers.
- Store timestamps in UTC.
- Treat date-only values as calendar dates, not timestamps.
- Use logging rather than `print()` for application diagnostics.

---

## Testing Rules

For every substantive change:

1. Add or update tests where behaviour changes.
2. Run the smallest relevant test set during development.
3. Run the full automated test suite before declaring the task complete.
4. Do not remove or weaken tests merely to make a change pass.

Critical areas that require tests include:

- Task hierarchy.
- Progress calculation.
- Dependency-cycle detection.
- Overdue/date logic.
- Database CRUD and transactions.
- Schema migrations.
- Backup and restore.
- Session lease behaviour.
- Cross-platform path handling.

UI testing should focus on important workflows rather than brittle pixel-level assertions.

---

## Database Rules

- SQLite is the application data store.
- SQLAlchemy 2.x is the preferred persistence layer.
- Alembic is used for schema migrations.
- UI classes must never issue SQL directly.
- Migrations must preserve existing user data.
- Never edit an existing released migration to change history; create a new migration.
- Do not assume SQLite WAL mode is appropriate for synchronised folders unless explicitly validated.
- Never implement automatic merging of conflicting SQLite database files.

---

## UI Rules

- PySide6 / Qt 6 is the UI framework.
- Follow the approved dark visual direction in `SPEC.md`.
- macOS and Windows should feel native while retaining a consistent FlowTrack identity.
- Prefer Qt's platform-aware shortcuts, dialogs, menus, and system behaviours.
- Preserve keyboard accessibility.
- Keep interactions responsive.
- Do not block the UI thread with slow filesystem/database work where that could be noticeable.

---

## Git & Change Discipline

- Keep changes scoped and reviewable.
- Do not rewrite unrelated files.
- Do not commit generated build artefacts, virtual environments, caches, local databases, backups, logs, or secrets.
- Keep `.gitignore` current.
- Do not alter Git history unless explicitly requested.
- When asked to commit, use a concise message describing the completed scope.

---

## Security & Privacy

- FlowTrack is local-first and should not require internet access for core functionality.
- Do not introduce telemetry, analytics, remote APIs, cloud services, or external data transmission unless explicitly approved.
- Do not place task descriptions or other user content in normal INFO-level logs unless necessary.
- Never commit credentials, tokens, personal data, local database files, or organisation-specific secrets.

---

## Completion Checklist

Before reporting a task as complete:

- [ ] Requested scope is fully implemented.
- [ ] Behaviour matches `SPEC.md`.
- [ ] No unrelated features were added.
- [ ] Relevant tests were added/updated.
- [ ] Full test suite passes.
- [ ] Application still launches.
- [ ] Cross-platform implications were considered.
- [ ] Database/data-safety implications were considered.
- [ ] Documentation was updated if setup, architecture, or behaviour changed.
- [ ] Summary clearly states what changed and any remaining limitations.

---

## When Unsure

Prefer, in order:

1. `SPEC.md`
2. Existing tests
3. Existing architecture and conventions
4. The smallest implementation that satisfies the current request

Do not make a broad architectural decision merely to resolve a small implementation problem.
