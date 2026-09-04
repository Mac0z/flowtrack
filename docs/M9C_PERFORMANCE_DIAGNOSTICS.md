# M9C Performance Diagnostics

## Purpose and workflow

Performance Diagnostics is lightweight instrumentation for finding real-world
latency in FlowTrack's task-save path. It is measurement only, not an analytics
or optimization feature. The intended workflow is:

1. Enable diagnostics in **Settings → Performance Diagnostics**.
2. Use FlowTrack normally for several days.
3. Export the retained diagnostics from Settings.
4. Analyse the real-world bottlenecks.
5. Make any optimization in a later, targeted pull request.

The setting defaults to **off** and persists as an application preference.
When off, timers short-circuit and no performance event file is written.

## Privacy and local storage

Diagnostics are local only. FlowTrack makes **no network transmission** of
these records and requires no service. The allow-listed JSON context contains
only booleans, numeric counts, and coarse categories. It never stores task or
project titles, descriptions, owner or tag text, paths, IDs, user or machine
names, email addresses, arbitrary UI text, or database contents.

Events contain a UTC timestamp, application version, platform, event name,
elapsed milliseconds, slow classification, and anonymous context. Files live
under FlowTrack's platform-aware application log area in the `performance`
subdirectory, outside the user-selected SQLite dataset. This resolves to the
normal Application Support location on macOS and Local AppData on Windows; no
platform path is hard-coded.

## Retention

The active `performance-diagnostics.jsonl` file rotates at 4 MiB. FlowTrack
retains the active file and two rotations, for approximately 12 MiB maximum.
Rotation and append are protected by an in-process lock. A write failure is
logged and ignored, and therefore cannot fail the measured user operation.

## Events and context

The initial task-write instrumentation records the real boundaries available
in the current architecture:

- `task_save.total`
- `task_save.validation`
- `task_save.dependency_validation`
- `task_save.task_write`
- `task_save.dependency_write`
- `task_save.project_update`
- `task_save.commit`
- `task_save.reload`
- `ui_refresh.my_tasks`
- `ui_refresh.project`
- `ui_refresh.dashboard`
- `ui_refresh.calendar`

`task_save.activity_write` and a standalone `ui_refresh.gantt` are reserved by
the recorder but are not emitted yet: the current task path has no activity
write, while Gantt refresh is currently coupled to the project refresh rather
than a clean independent boundary.

Context may contain `has_project`, `has_parent`, `is_completed`,
`dependency_count`, `child_count`, `status`, `save_type`,
`task_count_bucket`, and `dependency_count_bucket`. Only predefined status and
bucket values are accepted. Context that is not allow-listed is discarded.

Every operation with `duration_ms >= 150` has `slow: true`. This reflects the
SPEC target for common local edits and is a classification for analysis, not a
failure or timeout.

## Export, summary, and clear

**Export Performance Diagnostics** asks for a destination and creates a ZIP
without changing the originals. It contains every retained JSONL file plus
`performance-summary.json`, which reports count, minimum, p50, p90, p95,
maximum, slow count, and slow percentage for each event. Raw JSONL remains the
source of truth.

**Clear Performance Diagnostics** presents a confirmation whose safe default
is Cancel. Confirming deletes only the retained performance JSONL files. It
does not delete normal logs or user data.
