import json
import zipfile
from datetime import datetime, timezone

import pytest

from flowtrack.infrastructure.performance import (
    DIAGNOSTICS_FILENAME,
    PerformanceDiagnostics,
    percentile,
    summarize_events,
)


def test_disabled_diagnostics_emit_nothing(tmp_path):
    diagnostics = PerformanceDiagnostics(False, directory=tmp_path)
    with diagnostics.measure("task_save.total"):
        pass
    assert not tmp_path.exists() or not list(tmp_path.iterdir())


def test_enabled_event_shape_monotonic_timing_and_privacy(tmp_path):
    ticks = iter([20.0, 20.2])
    diagnostics = PerformanceDiagnostics(
        True, directory=tmp_path, clock=lambda: next(ticks),
        utc_now=lambda: datetime(2026, 9, 4, tzinfo=timezone.utc),
    )
    with diagnostics.measure("task_save.total", context={
        "has_project": True, "dependency_count": 3, "status": "in_progress",
        "task_title": "Secret title", "project_name": "Secret project", "bad": ["text"],
    }):
        pass
    event = json.loads((tmp_path / DIAGNOSTICS_FILENAME).read_text())
    assert event == {
        "app_version": event["app_version"], "context": {
            "dependency_count": 3, "has_project": True, "status": "in_progress",
        },
        "duration_ms": 200.0, "event": "task_save.total", "platform": event["platform"],
        "slow": True, "timestamp_utc": "2026-09-04T00:00:00Z",
    }
    raw = json.dumps(event)
    assert "Secret" not in raw and "task_title" not in raw and "project_name" not in raw


@pytest.mark.parametrize(("duration", "slow"), [(149.999, False), (150.0, True)])
def test_slow_threshold(tmp_path, duration, slow):
    diagnostics = PerformanceDiagnostics(True, directory=tmp_path)
    diagnostics.record("task_save.commit", duration)
    assert json.loads(diagnostics.active_path.read_text())["slow"] is slow


def test_rotation_is_bounded(tmp_path):
    diagnostics = PerformanceDiagnostics(True, directory=tmp_path, max_file_bytes=1,
                                         retained_file_count=3)
    for _ in range(8):
        diagnostics.record("task_save.total", 1)
    assert sorted(path.name for path in diagnostics.retained_paths()) == [
        DIAGNOSTICS_FILENAME, f"{DIAGNOSTICS_FILENAME}.1", f"{DIAGNOSTICS_FILENAME}.2",
    ]


def test_write_failure_is_safe(tmp_path, caplog):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("file")
    diagnostics = PerformanceDiagnostics(True, directory=blocked)
    diagnostics.record("task_save.total", 1)
    assert "could not be written" in caplog.text


def test_export_includes_raw_files_and_summary_and_clear_is_scoped(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "export"
    diagnostics = PerformanceDiagnostics(True, directory=source)
    diagnostics.record("task_save.total", 200)
    unrelated = source / "flowtrack.log"
    unrelated.write_text("keep")
    archive = diagnostics.export(destination)
    with zipfile.ZipFile(archive) as exported:
        assert DIAGNOSTICS_FILENAME in exported.namelist()
        summary = json.loads(exported.read("performance-summary.json"))
        assert summary["task_save.total"]["slow_count"] == 1
    diagnostics.clear()
    assert unrelated.read_text() == "keep"
    assert not diagnostics.retained_paths()


def test_percentiles_and_summary_calculations():
    assert percentile([0, 10, 20, 30, 40], 90) == pytest.approx(36)
    assert percentile([10, 20], 50) == 15
    with pytest.raises(ValueError):
        percentile([], 50)
    summary = summarize_events([
        {"event": "task_save.total", "duration_ms": value}
        for value in (10, 20, 30, 200)
    ])["task_save.total"]
    assert summary == {
        "count": 4, "min_ms": 10.0, "p50_ms": 25.0, "p90_ms": 149.0,
        "p95_ms": pytest.approx(174.5), "max_ms": 200.0, "slow_count": 1,
        "slow_percent": 25.0,
    }


def test_diagnostics_write_failure_does_not_fail_task_save(tmp_path):
    from sqlalchemy import create_engine, select

    from flowtrack.application.task_execution import TaskExecutionService
    from flowtrack.persistence.database import session_factory
    from flowtrack.persistence.models import Base, Task

    blocked = tmp_path / "not-a-directory"
    blocked.write_text("file")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    service = TaskExecutionService(
        session_factory(engine), PerformanceDiagnostics(True, directory=blocked)
    )
    task_id = service.create_task("content that must not enter diagnostics")
    service.update_task(task_id, title="still saved")
    with service._factory() as session:
        assert session.scalar(select(Task.title).where(Task.id == task_id)) == "still saved"


def test_task_save_records_real_service_phases(tmp_path):
    from sqlalchemy import create_engine

    from flowtrack.application.task_execution import TaskExecutionService
    from flowtrack.infrastructure.performance import read_events
    from flowtrack.persistence.database import session_factory
    from flowtrack.persistence.models import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    diagnostics = PerformanceDiagnostics(True, directory=tmp_path)
    service = TaskExecutionService(session_factory(engine), diagnostics)
    task_id = service.create_task("not recorded")
    service.update_task(task_id, title="also not recorded")
    events = read_events(diagnostics.retained_paths())
    names = [event["event"] for event in events]
    assert names.count("task_save.total") == 2
    assert names.count("task_save.validation") == 2
    assert names.count("task_save.task_write") == 2
    assert names.count("task_save.commit") == 2
    assert "not recorded" not in diagnostics.active_path.read_text()
