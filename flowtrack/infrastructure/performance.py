"""Privacy-preserving, local performance diagnostics.

The recorder deliberately accepts only a small allow-list of anonymous context
fields.  A caller cannot accidentally persist task text or entity identifiers.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
import zipfile
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from flowtrack import __version__
from flowtrack.infrastructure.paths import performance_diagnostics_directory
from flowtrack.infrastructure.platform import operating_system

logger = logging.getLogger(__name__)

DIAGNOSTICS_FILENAME = "performance-diagnostics.jsonl"
MAX_FILE_BYTES = 4 * 1024 * 1024
RETAINED_FILE_COUNT = 3
SLOW_THRESHOLD_MS = 150.0
ALLOWED_EVENTS = frozenset({
    "task_save.total", "task_save.validation", "task_save.dependency_validation",
    "task_save.task_write", "task_save.dependency_write", "task_save.commit",
    "task_save.reload", "task_save.project_update", "task_save.activity_write",
    "ui_refresh.my_tasks", "ui_refresh.project", "ui_refresh.dashboard",
    "ui_refresh.calendar", "ui_refresh.gantt",
    "inspector_save.total", "inspector_save.emit_refresh",
    "ui_refresh.project_views_total", "ui_refresh.execution_views_total",
    "ui_refresh.pinned_projects", "ui_refresh.inspector",
    "inspector_load.total", "inspector_load.task_detail", "inspector_load.owners",
    "inspector_load.tags", "inspector_load.dependencies",
    "inspector_load.widget_population", "ui_event_loop.resume_after_save",
})
_COUNT_FIELDS = frozenset({"dependency_count", "child_count"})
_BOOLEAN_FIELDS = frozenset({"has_project", "has_parent", "is_completed"})
_CATEGORIES: dict[str, frozenset[str]] = {
    "status": frozenset({"not_started", "in_progress", "blocked", "waiting", "complete", "cancelled"}),
    "save_type": frozenset({"create", "update"}),
    "task_count_bucket": frozenset({"0-99", "100-999", "1000-4999", "5000+"}),
    "dependency_count_bucket": frozenset({"0", "1", "2-4", "5+"}),
}


def _safe_context(context: Mapping[str, object] | None) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in (context or {}).items():
        if key in _BOOLEAN_FIELDS and type(value) is bool:
            result[key] = value
        elif key in _COUNT_FIELDS and type(value) is int and value >= 0:
            result[key] = value
        elif key in _CATEGORIES and isinstance(value, str) and value in _CATEGORIES[key]:
            result[key] = value
    return result


def _platform_name() -> str:
    try:
        return operating_system().value
    except ValueError:
        return sys.platform


class PerformanceDiagnostics:
    """Thread-safe bounded JSONL recorder which fails closed and silently."""

    def __init__(
        self,
        enabled: bool | Callable[[], bool] = False,
        *,
        directory: Path | None = None,
        max_file_bytes: int = MAX_FILE_BYTES,
        retained_file_count: int = RETAINED_FILE_COUNT,
        clock: Callable[[], float] = time.perf_counter,
        utc_now: Callable[[], datetime] | None = None,
    ) -> None:
        self._enabled = enabled if callable(enabled) else lambda: enabled
        self.directory = Path(directory) if directory is not None else performance_diagnostics_directory()
        self.max_file_bytes = max_file_bytes
        self.retained_file_count = retained_file_count
        self._clock = clock
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        try:
            return bool(self._enabled())
        except Exception:
            return False

    @property
    def active_path(self) -> Path:
        return self.directory / DIAGNOSTICS_FILENAME

    @contextmanager
    def measure(self, event: str, *, context: Mapping[str, object] | None = None) -> Iterator[None]:
        """Measure a real code boundary, or nearly free short-circuit when off."""
        if not self.enabled or event not in ALLOWED_EVENTS:
            yield
            return
        try:
            start = self._clock()
        except Exception:
            logger.warning("Performance diagnostics clock could not be read", exc_info=True)
            yield
            return
        try:
            yield
        finally:
            try:
                duration_ms = max(0.0, (self._clock() - start) * 1000)
            except Exception:
                logger.warning("Performance diagnostics clock could not be read", exc_info=True)
            else:
                self.record(event, duration_ms, context=context)

    def timer_start(self) -> float | None:
        """Return a diagnostics clock reading, or ``None`` when unavailable/off."""
        if not self.enabled:
            return None
        try:
            return self._clock()
        except Exception:
            logger.warning("Performance diagnostics clock could not be read", exc_info=True)
            return None

    def record_since(
        self, event: str, start: float | None, *, context: Mapping[str, object] | None = None,
    ) -> None:
        """Record elapsed time from ``start`` without allowing clock failure to escape."""
        if start is None:
            return
        try:
            duration_ms = max(0.0, (self._clock() - start) * 1000)
        except Exception:
            logger.warning("Performance diagnostics clock could not be read", exc_info=True)
            return
        self.record(event, duration_ms, context=context)

    def record(self, event: str, duration_ms: float, *, context: Mapping[str, object] | None = None) -> None:
        if not self.enabled or event not in ALLOWED_EVENTS:
            return
        event_data = {
            "timestamp_utc": self._utc_now().astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "app_version": __version__,
            "platform": _platform_name(),
            "event": event,
            "duration_ms": round(float(duration_ms), 3),
            "slow": duration_ms >= SLOW_THRESHOLD_MS,
            "context": _safe_context(context),
        }
        try:
            payload = json.dumps(event_data, separators=(",", ":"), sort_keys=True) + "\n"
            with self._lock:
                self.directory.mkdir(parents=True, exist_ok=True)
                self._rotate_if_needed(len(payload.encode("utf-8")))
                with self.active_path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(payload)
        except (OSError, TypeError, ValueError):
            logger.warning("Performance diagnostics event could not be written", exc_info=True)

    def retained_paths(self) -> list[Path]:
        paths = [self.active_path]
        paths.extend(self.directory / f"{DIAGNOSTICS_FILENAME}.{index}"
                     for index in range(1, self.retained_file_count))
        return [path for path in paths if path.is_file()]

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        if not self.active_path.exists() or self.active_path.stat().st_size + incoming_bytes <= self.max_file_bytes:
            return
        oldest = self.directory / f"{DIAGNOSTICS_FILENAME}.{self.retained_file_count - 1}"
        oldest.unlink(missing_ok=True)
        for index in range(self.retained_file_count - 2, 0, -1):
            source = self.directory / f"{DIAGNOSTICS_FILENAME}.{index}"
            if source.exists():
                source.replace(self.directory / f"{DIAGNOSTICS_FILENAME}.{index + 1}")
        self.active_path.replace(self.directory / f"{DIAGNOSTICS_FILENAME}.1")

    def clear(self) -> None:
        """Delete only FlowTrack performance records, never logs or user data."""
        try:
            with self._lock:
                for path in self.retained_paths():
                    path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Performance diagnostics could not be cleared", exc_info=True)
            raise

    def export(self, destination: Path) -> Path:
        """Copy retained raw events and a derived summary into one ZIP archive."""
        destination = Path(destination)
        if destination.suffix.lower() != ".zip":
            destination = destination.with_suffix(".zip")
        with self._lock:
            paths = self.retained_paths()
            events = read_events(paths)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in paths:
                    archive.write(path, arcname=path.name)
                archive.writestr("performance-summary.json", json.dumps(summarize_events(events), indent=2, sort_keys=True))
        return destination


def read_events(paths: Sequence[Path]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in paths:
        try:
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        item = json.loads(line)
                        if isinstance(item, dict) and isinstance(item.get("duration_ms"), (int, float)):
                            events.append(item)
                    except (json.JSONDecodeError, TypeError):
                        continue
        except OSError:
            logger.warning("Performance diagnostics file could not be read", exc_info=True)
    return events


def percentile(values: Sequence[float], percent: float) -> float:
    """Return a linearly interpolated percentile for 0 <= percent <= 100."""
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * percent / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarize_events(events: Sequence[Mapping[str, object]]) -> dict[str, dict[str, float | int]]:
    """Calculate portable per-event latency statistics from raw events."""
    groups: dict[str, list[float]] = defaultdict(list)
    for item in events:
        name, duration = item.get("event"), item.get("duration_ms")
        if isinstance(name, str) and isinstance(duration, (int, float)) and not isinstance(duration, bool):
            groups[name].append(float(duration))
    summary: dict[str, dict[str, float | int]] = {}
    for name, values in sorted(groups.items()):
        slow_count = sum(value >= SLOW_THRESHOLD_MS for value in values)
        summary[name] = {
            "count": len(values), "min_ms": min(values), "p50_ms": median(values),
            "p90_ms": round(percentile(values, 90), 3),
            "p95_ms": round(percentile(values, 95), 3),
            "max_ms": max(values), "slow_count": slow_count,
            "slow_percent": round(slow_count * 100 / len(values), 1),
        }
    return summary
