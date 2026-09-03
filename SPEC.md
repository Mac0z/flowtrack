# FlowTrack --- Product & Build Specification

**Version:** 1.1\
**Status:** Source of Truth / implementation baseline\
**Date:** 29 August 2026\
**Platforms:** macOS and Windows\
**Technology baseline:** Python 3.12, PySide6 / Qt 6, SQLite

> This document defines what FlowTrack is, how it should behave, and the
> architectural boundaries for implementation. Codex and human
> contributors should treat it as the product and engineering source of
> truth. Core behaviour or architectural decisions should be updated
> here before implementation diverges from the specification.

------------------------------------------------------------------------

## 1. Product Definition

FlowTrack is a single-user, work-focused desktop task and project
management application designed to make both strategic, long-running
objectives and short-term operational work easy to manage from one
place.

The product should feel closer to a premium professional productivity
application than a traditional internal utility: fast, visually calm,
keyboard-friendly, information-dense when required, and enjoyable to use
every day.

FlowTrack must be a **native-feeling cross-platform desktop application
supporting macOS and Windows from a single source codebase**. Neither
platform is considered a secondary port.

### 1.1 Product principles

-   One system for projects, objectives, tasks and subtasks.
-   Hierarchy without bureaucracy: a task may be standalone or contain
    child tasks.
-   Progress should be visible, meaningful and easy to maintain.
-   Delegation must be first-class even though the application itself is
    single-user.
-   Planning views and daily execution views must use the same
    underlying data.
-   Local-first: no server, account, cloud backend or subscription is
    required.
-   Portable data: the user chooses the database location, including a
    OneDrive-synchronised folder.
-   Cross-platform by design: no platform-specific assumptions in core
    application logic.
-   Fast capture: adding a small task should take seconds.
-   Power features should stay out of the way until needed.
-   Visual quality is a product requirement, not optional polish.

### 1.2 Non-goals for v1

-   Multi-user concurrent editing or collaborative accounts.
-   A hosted web service or mobile application.
-   Email, Slack, Teams, Jira or calendar integrations.
-   Complex resource/capacity planning.
-   Timesheets, billing or expense management.
-   Enterprise permissions or role-based access control.
-   Real-time database synchronisation between computers.

------------------------------------------------------------------------

## 2. Core Concepts & Data Model

The core modelling decision is that work items are hierarchical.
Projects provide a top-level container, while tasks can recursively
contain child tasks. A task does not change type merely because it is
large or small.

### 2.1 Project

A Project groups related work and supplies project-level metadata,
progress, colour and planning context.

  Field                         Type        Notes
  ----------------------------- ----------- --------------------------------------------------
  `id`                          UUID        Stable identifier
  `name`                        Text        Required
  `description`                 Text        Optional
  `status`                      Enum        Planned / Active / On Hold / Complete / Archived
  `colour`                      Text        UI category colour
  `start_date`                  Date        Optional
  `due_date`                    Date        Optional
  `progress_mode`               Enum        Automatic / Manual
  `manual_progress`             Integer     0--100 when manual
  `is_pinned`                   Boolean     Navigation shortcut
  `created_at` / `updated_at`   Timestamp   Audit metadata

### 2.2 Task

  -----------------------------------------------------------------------
  Field                   Type                    Notes
  ----------------------- ----------------------- -----------------------
  `id`                    UUID                    Stable identifier

  `project_id`            UUID?                   Null for standalone
                                                  tasks

  `parent_task_id`        UUID?                   Self-reference enabling
                                                  hierarchy

  `title`                 Text                    Required

  `description`           Text                    Optional

  `owner_id`              UUID?                   Assigned person

  `status`                Enum                    Not Started / In
                                                  Progress / Blocked /
                                                  Waiting / Complete /
                                                  Cancelled

  `priority`              Enum                    Low / Medium / High /
                                                  Critical

  `start_date` /          Date                    Either may be null
  `due_date`                                      

  `progress_mode`         Enum                    Automatic / Manual

  `manual_progress`       Integer                 0--100

  `sort_order`            Integer                 Stable sibling ordering

  `is_milestone`          Boolean                 Milestone
                                                  representation on Gantt

  `created_at` /          Timestamp               Audit metadata
  `updated_at` /                                  
  `completed_at`                                  
  -----------------------------------------------------------------------

### 2.3 Supporting entities

-   **Owner:** Name, initials/avatar colour, optional role/team and
    active flag. Owners represent delegation; they do not log in.
-   **Tag:** Reusable text label with optional colour.
-   **TaskTag:** Many-to-many link between tasks and tags.
-   **Dependency:** Directed task relationship. v1 supports
    Finish-to-Start dependencies.
-   **Activity:** Local audit trail for meaningful changes such as
    completion, reassignment and due-date changes.

### 2.4 Progress calculation

Automatic progress is calculated from immediate children.

-   Completed leaf task = 100%.
-   Incomplete leaf task defaults to 0% unless manual percentage
    progress is enabled.
-   Parent progress is the arithmetic mean of its non-cancelled
    immediate children in v1.
-   Cancelled tasks are excluded from automatic progress calculations.
-   A project in Automatic mode derives progress from its top-level
    tasks.
-   Manual mode overrides the calculated value.

Future versions may introduce weighted progress or effort estimates.

------------------------------------------------------------------------

## 3. Information Architecture

Primary navigation:

-   Dashboard
-   My Tasks
-   Projects
-   Calendar
-   Timeline / Gantt
-   Reports
-   Settings

### 3.1 Dashboard

The dashboard is the default landing screen and should answer:

-   What needs my attention?
-   How is my work progressing?
-   What is late?
-   What is coming next?

The dashboard includes:

-   Greeting and compact global search.
-   KPI cards: Active Projects, In Progress, Completed, Overdue.
-   My Tasks panel with configurable quick filter; default is Due This
    Week.
-   Project Overview with progress, task counts and due dates.
-   Pinned projects.
-   Quick Add Task without leaving the screen.

### 3.2 My Tasks

A high-speed execution view for standalone tasks and tasks across all
projects.

Default sorting prioritises:

1.  Overdue.
2.  Due soon.
3.  Priority.
4.  User-defined ordering.

Capabilities:

-   List view with status, priority, project, owner and due date.
-   Filters for status, priority, project, owner, tags and date window.
-   Saved filter state between launches.
-   Inline completion and quick edits.
-   Search-as-you-type.

### 3.3 Projects

Projects can be displayed as cards or a compact list.

Opening a project exposes:

-   Overview
-   List
-   Board
-   Gantt

Board is a status-based Kanban representation of the same underlying
tasks.

### 3.4 Task Detail

Task details should normally open in a right-hand inspector where window
size permits, avoiding unnecessary navigation.

The inspector exposes:

-   Title
-   Description
-   Status
-   Owner
-   Priority
-   Start date
-   Due date
-   Progress
-   Tags
-   Dependencies
-   Child tasks
-   Activity

A task becomes a parent simply by adding a child. No explicit
Epic/Subtask type is required.

### 3.5 Calendar

Month/week-oriented planning view displaying tasks by due date and
optionally start date.

Dragging a task to another date may update its due date, provided an
Undo or confirmation mechanism is available.

### 3.6 Gantt / Timeline

Gantt is a core product feature and should be visually polished rather
than treated as an export/report.

Requirements:

-   Expandable hierarchical task rows.
-   Day / Week / Month zoom.
-   Today marker.
-   Bars spanning start-to-due dates.
-   Distinct milestone representation.
-   Progress indication within bars.
-   Finish-to-Start dependency connectors.
-   Drag bar to move dates.
-   Resize handles to adjust start/due date.
-   Non-drag date editing in the task inspector.
-   Horizontal timeline scrolling with frozen task/owner columns.
-   Collapsed parent rows summarise the date span of their children.
-   Clear overdue/blocked visual states without overwhelming the
    interface.

------------------------------------------------------------------------

## 4. Interaction & Visual Design

The approved mock-up establishes the visual direction: dark professional
shell, restrained purple accent, high-contrast typography, subtle
borders, compact data presentation and colour used primarily for
status/category meaning.

### 4.1 Design requirements

-   FlowTrack uses a token-based theme architecture. The initial/default
    built-in theme is Dark; a Light theme may be added later.
-   Views and widgets consume semantic theme tokens rather than hard-coded
    visual colours wherever practical. Theme definitions must support future
    built-in and validated user-created themes without requiring view rewrites.
-   A Light theme and user-facing custom-theme editor are outside M3 scope.
-   Sidebar remains visually quiet and supports pinned projects.
-   Rounded surfaces and subtle elevation.
-   Avoid excessive gradients, glow or decorative effects.
-   Animations should be short and functional, approximately 120--200
    ms.
-   Destructive actions require confirmation or reliable Undo.
-   Confirmation defaults reflect the action's risk: routine, reversible
    actions such as moving or rescheduling a task default to the affirmative
    action, while Escape cancels without making changes. Destructive or
    difficult-to-reverse actions default to the safest non-destructive choice.
-   Completed work remains accessible without visually dominating active
    work.
-   Layout must adapt cleanly to common laptop and desktop resolutions
    on both platforms.
-   Minimum comfortable target: approximately 1366×768.
-   Optimised for 1920×1080 and above.
-   macOS and Windows should feel native to their respective
    environments while retaining a consistent FlowTrack identity.

### 4.2 Keyboard behaviour

Use Qt's platform-aware standard shortcut handling wherever possible.

Conceptual shortcuts:

  Action                      macOS   Windows
  --------------------------- ------- ----------
  Quick task                  `⌘N`    `Ctrl+N`
  Global search / command     `⌘K`    `Ctrl+K`
  Search/filter active view   `⌘F`    `Ctrl+F`
  Close inspector/dialog      `Esc`   `Esc`

Do not hard-code Control/Command behaviour where Qt provides a
platform-aware abstraction.

### 4.3 Quick capture

Quick capture opens a compact task creation surface.

Title is the only required field.

Optional fast fields:

-   Project
-   Owner
-   Due date
-   Priority

Natural-language capture is deferred.

### 4.4 Status semantics

  Status        Meaning
  ------------- --------------------------------------------------------
  Not Started   Work has not begun
  In Progress   Actively being worked
  Blocked       Cannot progress because of an impediment
  Waiting       Awaiting another person/event
  Complete      Finished; progress = 100%
  Cancelled     Intentionally abandoned; excluded from normal progress

------------------------------------------------------------------------

## 5. Technical Architecture

FlowTrack is a cross-platform desktop application. The architecture must
keep UI, business rules and persistence separate so features can be
tested independently and coding agents can modify one layer without
destabilising others.

### 5.1 Technology baseline

-   Python 3.12
-   PySide6 6.7.3/ Qt 6.7
-   SQLite.
-   SQLAlchemy 2.x for persistence.
-   Alembic for schema migrations.
-   pytest for unit/integration tests.
-   PyInstaller initially for application packaging, subject to
    validation on both platforms.
-   Python standard logging with rotating local log files.
-   Git source control.

Dependencies should be kept deliberately small.

### 5.2 Target package structure

``` text
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
```

### 5.3 Architectural rules

-   UI widgets must not execute raw SQL.
-   Business rules live outside view classes.
-   Repositories own persistence operations.
-   All multi-record writes are transactional.
-   Database schema changes are versioned migrations.
-   Domain identifiers use UUIDs rather than user-visible row numbers.
-   Dates are stored in ISO-8601 form.
-   Timestamps use UTC.
-   The application must remain usable with no internet connection.
-   Core code must contain no hard-coded Windows or macOS filesystem
    paths.
-   Use `pathlib` for filesystem paths.
-   OS-specific behaviour must be isolated behind
    infrastructure/platform helpers.
-   Prefer Qt's platform abstractions for menus, shortcuts, dialogs,
    icons and system integration.
-   Platform-specific code requires a documented reason and appropriate
    tests where practical.


## 5.4 Compatibility baseline:
- macOS 11 Big Sur or later, Intel and Apple Silicon
- Windows 10/11 x86-64
- FlowTrack must remain compatible with PySide6 6.7.3 APIs.
- Do not introduce dependencies requiring macOS 12+.

------------------------------------------------------------------------

## 6. Cross-Platform Requirements

macOS and Windows are equal supported targets.

### 6.1 Development model

Initial development may occur on macOS. This must not result in
macOS-specific assumptions being embedded in the application.

The same Git repository and Python source are used for both platforms.

### 6.2 macOS

Target deliverables:

-   `FlowTrack.app`
-   Distributable `.dmg` or equivalent signed release package in a later
    release process.

FlowTrack should respect normal macOS conventions for:

-   Menu placement.
-   Command-key shortcuts.
-   File/folder selection.
-   Application support/configuration locations.
-   Window behaviour.
-   Retina/high-DPI rendering.

### 6.3 Windows

Target deliverables:

-   `FlowTrack.exe`
-   User-friendly installer/package in the release process.

FlowTrack should respect normal Windows conventions for:

-   Control-key shortcuts.
-   File/folder selection.
-   Application data/configuration locations.
-   Window behaviour.
-   High-DPI rendering.

### 6.4 Build principle

Do not assume a macOS-built executable can simply be distributed to
Windows or vice versa.

Release artefacts should be built and tested on their target OS.
Automated cross-platform build pipelines may be added later.

------------------------------------------------------------------------

## 7. Local Database, OneDrive & Data Safety

The user may place the FlowTrack data directory inside OneDrive.

SQLite is suitable for the single-user model, but OneDrive is a file
synchronisation system rather than a database replication system.
FlowTrack must actively protect the data file.

### 7.1 Data directory

The application executable/app bundle is separate from user data.

The user selects a FlowTrack data directory such as:

``` text
FlowTrackData/
  flowtrack.db
  backups/
  attachments/   # reserved for future use
  .flowtrack-session.json
```

The data directory may be:

-   A normal local folder.
-   A OneDrive-synchronised folder.
-   Another user-managed synchronised folder, provided the same
    single-writer constraints are understood.

FlowTrack should not depend on recognising a specific OneDrive path.

### 7.2 Cross-platform path handling

Examples only:

macOS:

``` text
~/Library/CloudStorage/OneDrive-Organisation/FlowTrackData/
```

Windows:

``` text
C:\Users\<user>\OneDrive - Organisation\FlowTrackData\
```

These paths must never be hard-coded.

### 7.3 Single-writer safety

FlowTrack is single-user, but the same synced dataset could exist on
multiple computers.

A simple operating-system file lock is insufficient because OneDrive
clients on different machines do not share a true distributed lock.

FlowTrack therefore uses two layers:

1.  **Local process lock** --- prevents multiple local FlowTrack
    processes from writing the same database.
2.  **Dataset session lease** --- a small session file alongside the
    database identifies the machine/application instance that currently
    appears to own write access.

The session lease should contain, at minimum:

-   Application instance UUID.
-   Non-sensitive machine identifier.
-   Platform.
-   FlowTrack version.
-   Session start timestamp.
-   Last heartbeat timestamp.

### 7.4 Session lease behaviour

-   Opening a dataset for writing creates/claims a lease.
-   While FlowTrack is running, the lease heartbeat is refreshed
    periodically.
-   Normal shutdown releases the lease.
-   If another apparently active machine owns the lease, FlowTrack must
    not silently enter write mode.
-   The user may be offered read-only access where practical.
-   A stale lease may be recovered through an explicit recovery
    workflow.
-   Recovery must explain the risk that another computer could still
    have FlowTrack open.
-   FlowTrack must never claim that the lease mechanism guarantees
    distributed locking; it is a defensive safety mechanism.

### 7.5 Backup and integrity requirements

-   Run SQLite integrity checks at appropriate startup/recovery points.
-   Create automatic timestamped backups before schema migrations.
-   Create at least one backup per day when changes occur.
-   Default retention: 30 daily backups.
-   Provide **Backup Now**.
-   Provide **Restore Backup**.
-   Provide **Open Data Folder**.
-   Provide **Change Data Location**.
-   **Change Data Location** lets the user either safely copy the current
    dataset to a new directory or select an existing FlowTrack dataset. A copy
    preserves the original as a safety copy; FlowTrack never silently merges or
    overwrites SQLite datasets. The selected location becomes active only after
    restart and passes through the normal local-lock, lease, conflict, integrity,
    migration, backup and journal-safety startup flow.
-   Preserve the current database before a restore.
-   Validate the restored database before adopting it.
-   Never auto-merge conflicting SQLite databases.

### 7.6 Sync conflict detection

FlowTrack should inspect the data directory for suspicious
alternate/conflict copies of the database where feasible.

If a likely conflict is detected:

-   Warn the user prominently.
-   Do not automatically choose a winner.
-   Preserve all files.
-   Offer clear recovery guidance.

### 7.7 SQLite journal mode

Do not assume WAL mode is appropriate for cloud-synchronised storage.

The implementation must test and document the selected SQLite journal
configuration. Prefer conservative durability and recoverability over
theoretical write throughput; FlowTrack's workload does not require high
transaction throughput.

------------------------------------------------------------------------

## 8. Functional Requirements

  -----------------------------------------------------------------------
  ID                                  Requirement
  ----------------------------------- -----------------------------------
  FR-001                              Create, edit, complete, cancel and
                                      delete tasks

  FR-002                              Create and manage projects

  FR-003                              Nest tasks to arbitrary practical
                                      depth

  FR-004                              Assign any task to a locally
                                      configured owner

  FR-005                              Set status, priority, start date,
                                      due date, progress and tags

  FR-006                              Calculate automatic parent/project
                                      progress

  FR-007                              Create Finish-to-Start dependencies
                                      and reject dependency cycles

  FR-008                              Show overdue and due-soon work
                                      consistently across views

  FR-009                              Search tasks and projects by
                                      title/description

  FR-010                              Filter task lists by core metadata

  FR-011                              Display and edit project work on a
                                      hierarchical Gantt

  FR-012                              Display project work as a status
                                      Kanban board

  FR-013                              Provide a calendar planning view

  FR-014                              Persist view preferences and pinned
                                      projects

  FR-015                              Maintain automatic backups and
                                      support restore

  FR-016                              Export project/task data to CSV

  FR-017                              Archive projects without deleting
                                      historical data

  FR-018                              Provide an activity history for
                                      meaningful task changes

  FR-019                              Allow the user to choose/change the
                                      active data directory

  FR-020                              Protect datasets with local locking
                                      and cross-machine session lease
                                      checks

  FR-021                              Support read-only/recovery
                                      behaviour when another active lease
                                      is detected, where practical
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 9. Non-Functional Requirements

-   **NFR-001 Performance:** Common local navigation and edits should
    feel immediate; target \<150 ms for typical operations.
-   **NFR-002 Scale:** Comfortably support at least 100 projects and
    25,000 tasks.
-   **NFR-003 Reliability:** Unexpected termination must not normally
    corrupt committed data.
-   **NFR-004 Startup:** Target \<3 seconds on a typical current
    business computer, excluding slow cloud-file hydration.
-   **NFR-005 Offline:** All core features function without network
    access.
-   **NFR-006 Packaging:** End users must not need Python installed.
-   **NFR-007 Accessibility:** Keyboard operation for core workflows and
    sufficient contrast.
-   **NFR-008 Maintainability:** Domain and persistence layers require
    automated tests; critical calculations and migrations require tests.
-   **NFR-009 Observability:** Rotating diagnostic log with timestamps,
    severity and exception traces. Normal INFO logs should not contain
    task descriptions unnecessarily.
-   **NFR-010 Cross-platform:** The automated test suite must run on
    macOS and Windows.
-   **NFR-011 UI consistency:** Platform differences must not alter core
    product behaviour or data semantics.
-   **NFR-012 Portability:** A valid FlowTrack data directory created on
    macOS must be usable by the Windows application and vice versa after
    synchronisation and clean closure.
-   **NFR-013 High DPI:** UI must render correctly on Retina and Windows
    high-DPI displays.

------------------------------------------------------------------------

## 10. v1 Acceptance Criteria

FlowTrack v1 is acceptable when all of the following are true:

-   A fresh install on macOS can create/select a data directory,
    initialise a database and reach the Dashboard.
-   A fresh install on Windows can do the same.
-   A user can create a project, add nested tasks, assign different
    owners, dates and priorities, and see calculated progress.
-   Completing a child task updates parent/project progress without
    restarting.
-   The same project is represented consistently in List, Board and
    Gantt.
-   Gantt hierarchy can expand/collapse and date changes persist
    correctly.
-   A dependency cycle cannot be saved.
-   Overdue tasks are correctly identified using local calendar dates.
-   Closing and reopening preserves data, filters, pinned projects and
    appropriate window preferences.
-   A second local process cannot silently write the same database.
-   An apparently active lease from another computer prevents silent
    write access.
-   Stale-lease recovery requires an explicit user decision.
-   Backup Now creates a valid restorable backup.
-   Restore Backup preserves the pre-restore database.
-   A database cleanly closed on macOS can subsequently be opened on
    Windows, and vice versa.
-   The packaged macOS build runs without a separate Python
    installation.
-   The packaged Windows build runs without a separate Python
    installation.
-   Platform-appropriate keyboard shortcuts work.
-   Retina/high-DPI rendering is visually correct.
-   Automated tests pass on both supported platforms before release.

------------------------------------------------------------------------

## 11. Delivery Plan for Codex

Codex should implement FlowTrack in controlled milestones. Each
milestone must leave the repository runnable, tested and coherent.

Do **not** ask Codex to build the entire application in a single task.

### M0 --- Repository & cross-platform skeleton

Deliver:

-   Git repository structure.
-   Python project/dependency configuration.
-   Test harness.
-   Logging.
-   Empty PySide6 application shell.
-   Platform/path abstraction.
-   macOS and Windows compatibility assumptions documented.
-   Basic CI/test configuration where appropriate.

### M1 --- Persistence foundation

Deliver:

-   SQLite setup.
-   SQLAlchemy models.
-   Alembic migrations.
-   Project, Task, Owner, Tag and Dependency schema.
-   Repositories.
-   Transactions.
-   Persistence tests.

### M2 --- Domain rules

Deliver:

-   Task hierarchy.
-   Progress calculation.
-   Status semantics.
-   Overdue logic.
-   Dependency cycle detection.
-   Domain tests.

### M3 --- Application shell

Deliver:

-   Sidebar.
-   Navigation.
-   Dark theme tokens.
-   Reusable controls.
-   Settings persistence.
-   Command/search shell.
-   Platform-aware shortcuts.

### M4 --- Task execution

Deliver:

-   Dashboard.
-   My Tasks.
-   Quick capture.
-   Task inspector.
-   Filters.
-   Owner/tag management.

### M5 --- Projects

Deliver:

-   Project list/overview.
-   Hierarchical task list.
-   Progress visualisation.
-   Archive/pin behaviour.

### M6 --- Board & Calendar

Deliver:

-   Status Kanban board.
-   Task movement/status changes.
-   Calendar.
-   Due-date editing.

### M7 --- Gantt

Deliver:

-   Custom Gantt model/view.
-   Hierarchy.
-   Zoom.
-   Today marker.
-   Drag/resize.
-   Progress bars.
-   Milestones.
-   Dependency connectors.

### M8 --- Data safety & portability

Deliver:

-   Local database lock.
-   Dataset session lease.
-   Lease heartbeat/recovery.
-   Sync-conflict checks.
-   Automatic backups.
-   Integrity checks.
-   Restore workflow.
-   Cross-platform dataset portability tests.

### M9 --- Polish, packaging & release validation

Deliver:

-   Keyboard/interaction polish.
-   Undo/confirmation flows.
-   Performance profiling.
-   Accessibility pass.
-   macOS application build.
-   Windows application build.
-   Clean-machine smoke testing.
-   Cross-platform release checklist.

------------------------------------------------------------------------

## 12. Codex Working Rules

Codex must:

-   Read this specification before changing architecture or behaviour.
-   Implement only the requested milestone/scope unless explicitly
    instructed otherwise.
-   Not silently change requirements to simplify implementation.
-   Keep changes scoped and reviewable.
-   Add/update tests with domain and persistence changes.
-   Run relevant tests before declaring work complete.
-   Keep the full suite passing.
-   Avoid introducing network/cloud dependencies for core functionality.
-   Prefer clear, maintainable code over clever abstractions.
-   Use cross-platform APIs by default.
-   Avoid hard-coded filesystem paths.
-   Avoid Windows-only or macOS-only dependencies unless explicitly
    approved.
-   Record ambiguities and propose a decision rather than inventing
    major product behaviour.
-   Update developer documentation when setup/build procedures change.
-   Never make destructive database recovery decisions automatically.
-   Preserve backward compatibility with existing FlowTrack data unless
    a migration explicitly handles the change.

------------------------------------------------------------------------

## 13. Testing Strategy

### 13.1 Unit tests

Cover:

-   Progress calculations.
-   Hierarchy rules.
-   Status transitions where rules exist.
-   Overdue/due-soon calculations.
-   Dependency cycle detection.
-   Path/platform helpers.
-   Lease expiry/recovery decisions.

### 13.2 Persistence tests

Cover:

-   CRUD.
-   Transactions.
-   Hierarchical queries.
-   Migrations.
-   Backup validation.
-   Restore safety.
-   Database portability.

### 13.3 UI tests

Prioritise high-value workflows rather than brittle pixel-level tests:

-   Launch.
-   Create task.
-   Create project.
-   Edit task.
-   Complete task.
-   Navigate views.
-   Open/close inspector.

### 13.4 Platform testing

Before release:

-   Run automated tests on macOS.
-   Run automated tests on Windows.
-   Build native package on each target OS.
-   Smoke-test each packaged application.
-   Test a database moved/synchronised from macOS to Windows.
-   Test a database moved/synchronised from Windows to macOS.

------------------------------------------------------------------------

## 14. Deferred / Post-v1 Ideas

-   Light theme and appearance customisation.
-   Recurring tasks.
-   Natural-language quick capture.
-   Notifications/reminders.
-   Task/project templates.
-   Weighted progress and effort estimates.
-   Critical path analysis.
-   Additional dependency types.
-   Attachments and richer notes.
-   Outlook/Teams/Jira integrations.
-   Import from common task managers.
-   Optional encryption.
-   Portable/no-install Windows mode.
-   macOS menu-bar quick capture.
-   Cross-device sync service specifically designed for FlowTrack.
-   Mobile companion application.

------------------------------------------------------------------------

## 15. Decision Log

  ------------------------------------------------------------------------
  ID                      Decision                Rationale
  ----------------------- ----------------------- ------------------------
  D-001                   Native desktop rather   Best fit for
                          than web                standalone/local-first
                                                  operation and premium
                                                  desktop UX

  D-002                   Python + PySide6        Rapid implementation,
                                                  strong Qt capabilities
                                                  and good coding-agent
                                                  fit

  D-003                   SQLite                  Transactional, portable,
                                                  simple persistence
                                                  suited to one active
                                                  writer

  D-004                   Hierarchical task model Supports strategic and
                                                  small work without
                                                  artificial
                                                  Epic/Task/Subtask types

  D-005                   Owners are local        Delegation tracking
                          entities                without accounts or
                                                  collaboration complexity

  D-006                   macOS and Windows are   Prevents a later port
                          equal targets           and keeps the source
                                                  architecture genuinely
                                                  cross-platform

  D-007                   User-selected data      Separates application
                          directory               installation from
                                                  portable user data

  D-008                   OneDrive supported      Useful portability
                          defensively             without pretending file
                                                  sync is database
                                                  replication

  D-009                   Local lock + dataset    Adds protection against
                          session lease           both same-machine and
                                                  cross-machine accidental
                                                  concurrent use

  D-010                   Gantt is core v1        Long-term work requires
                                                  timeline/dependency
                                                  visualisation and it
                                                  forms part of
                                                  FlowTrack's identity

  D-011                   Target-platform builds  macOS and Windows
                                                  packages are
                                                  built/tested on their
                                                  respective operating
                                                  systems
  ------------------------------------------------------------------------

------------------------------------------------------------------------

## 16. Definition of Done

FlowTrack v1 is complete when:

1.  All v1 acceptance criteria are satisfied.
2.  All automated tests pass on macOS and Windows.
3.  Both packaged applications pass clean-machine smoke tests.
4.  Cross-platform database portability has been exercised.
5.  Database backup and restore has been exercised.
6.  Session lease and stale-session recovery have been exercised.
7.  No critical or high-severity known defects remain.
8.  The released UI meets the approved FlowTrack visual direction.
9.  This document accurately describes the released behaviour.

------------------------------------------------------------------------

**END OF SOURCE OF TRUTH --- v1.1**
