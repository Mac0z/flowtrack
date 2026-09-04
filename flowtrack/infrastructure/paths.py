"""Cross-platform locations for FlowTrack-owned application files."""

import os
from collections.abc import Mapping
from pathlib import Path

from flowtrack.infrastructure.platform import OperatingSystem, operating_system

APPLICATION_DIRECTORY_NAME = "FlowTrack"


def application_data_directory(
    *,
    platform_name: str | None = None,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the conventional per-user directory for application-owned data.

    Arguments are injectable so platform behavior can be tested on any host.
    This directory is not the future user-selected portable dataset directory.
    """
    variables = os.environ if environment is None else environment
    user_home = Path.home() if home is None else home
    system = operating_system(platform_name)

    if system is OperatingSystem.MACOS:
        return user_home / "Library" / "Application Support" / APPLICATION_DIRECTORY_NAME
    if system is OperatingSystem.WINDOWS:
        local_app_data = variables.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else user_home / "AppData" / "Local"
        return base / APPLICATION_DIRECTORY_NAME

    xdg_data_home = variables.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else user_home / ".local" / "share"
    return base / "flowtrack"


def log_directory(**kwargs: object) -> Path:
    """Return the directory for rotating diagnostic logs."""
    return application_data_directory(**kwargs) / "logs"


def performance_diagnostics_directory(**kwargs: object) -> Path:
    """Return the local, non-dataset directory for performance diagnostics."""
    return log_directory(**kwargs) / "performance"


def default_database_path(**kwargs: object) -> Path:
    """Return the replaceable M4 local dataset location."""
    return application_data_directory(**kwargs) / "flowtrack.db"
