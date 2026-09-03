"""Defensive cross-machine dataset session lease support.

The lease is deliberately not described as a distributed lock. A heartbeat is
considered stale after three minutes; writers refresh it every 30 seconds.
"""

import json
import os
import platform
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from flowtrack import __version__

STALE_AFTER = timedelta(minutes=3)
HEARTBEAT_INTERVAL_MS = 30_000


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def machine_identifier() -> str:
    """Return a stable opaque identifier without exposing host/user names."""
    value = f"{platform.system()}:{uuid.getnode()}".encode()
    import hashlib
    return hashlib.sha256(value).hexdigest()[:24]


@dataclass(frozen=True)
class SessionLease:
    instance_id: str
    machine_id: str
    platform: str
    flowtrack_version: str
    session_started_utc: str
    last_heartbeat_utc: str

    @classmethod
    def create(cls, instance_id: str, *, now: datetime | None = None) -> "SessionLease":
        timestamp = iso_utc(now or utc_now())
        return cls(instance_id, machine_identifier(), platform.system(), __version__, timestamp, timestamp)


class LeaseState(Enum):
    ABSENT = "absent"
    OWNED_BY_THIS_INSTANCE = "owned_by_this_instance"
    ACTIVE_OTHER_INSTANCE = "active_other_instance"
    STALE_OTHER_INSTANCE = "stale_other_instance"
    MALFORMED = "malformed"


@dataclass(frozen=True)
class LeaseEvaluation:
    state: LeaseState
    lease: SessionLease | None = None


class LeaseStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def evaluate(self, instance_id: str, *, now: datetime | None = None) -> LeaseEvaluation:
        if not self.path.exists():
            return LeaseEvaluation(LeaseState.ABSENT)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            lease = SessionLease(**data)
            heartbeat = datetime.fromisoformat(lease.last_heartbeat_utc.replace("Z", "+00:00"))
            if heartbeat.tzinfo is None:
                raise ValueError("timestamp lacks timezone")
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return LeaseEvaluation(LeaseState.MALFORMED)
        if lease.instance_id == instance_id:
            return LeaseEvaluation(LeaseState.OWNED_BY_THIS_INSTANCE, lease)
        age = (now or utc_now()) - heartbeat.astimezone(timezone.utc)
        state = LeaseState.STALE_OTHER_INSTANCE if age > STALE_AFTER else LeaseState.ACTIVE_OTHER_INSTANCE
        return LeaseEvaluation(state, lease)

    def claim(self, instance_id: str, *, now: datetime | None = None) -> SessionLease:
        lease = SessionLease.create(instance_id, now=now)
        self._atomic_write(lease)
        return lease

    def heartbeat(self, instance_id: str, *, now: datetime | None = None) -> bool:
        result = self.evaluate(instance_id, now=now)
        if result.state is not LeaseState.OWNED_BY_THIS_INSTANCE or result.lease is None:
            return False
        lease = SessionLease(**{**asdict(result.lease), "last_heartbeat_utc": iso_utc(now or utc_now())})
        self._atomic_write(lease)
        return True

    def release(self, instance_id: str) -> bool:
        if self.evaluate(instance_id).state is not LeaseState.OWNED_BY_THIS_INSTANCE:
            return False
        try:
            self.path.unlink()
        except FileNotFoundError:
            return False
        return True

    def _atomic_write(self, lease: SessionLease) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(asdict(lease), stream, indent=2, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            Path(temporary).replace(self.path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
