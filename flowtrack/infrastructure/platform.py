"""Normalized platform information for infrastructure integrations."""

import platform as platform_module
import sys
from dataclasses import dataclass
from enum import StrEnum


class OperatingSystem(StrEnum):
    """Operating systems understood by FlowTrack infrastructure."""

    MACOS = "macos"
    WINDOWS = "windows"
    OTHER = "other"


def operating_system(platform_name: str | None = None) -> OperatingSystem:
    """Return a stable OS value for a Python platform identifier."""
    name = platform_name or sys.platform
    if name == "darwin":
        return OperatingSystem.MACOS
    if name == "win32":
        return OperatingSystem.WINDOWS
    return OperatingSystem.OTHER


@dataclass(frozen=True, slots=True)
class PlatformInfo:
    """Non-sensitive runtime details suitable for diagnostics."""

    operating_system: OperatingSystem
    release: str
    machine: str


def current_platform() -> PlatformInfo:
    """Describe the current host using Python's cross-platform APIs."""
    return PlatformInfo(operating_system(), platform_module.release(), platform_module.machine())

