"""Stable application identity and installed/frozen version discovery."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib

APPLICATION_NAME = "FlowTrack"
ORGANIZATION_NAME = "FlowTrack"
BUNDLE_IDENTIFIER = "com.flowtrack.app"


def application_version() -> str:
    """Return package metadata embedded by installation and PyInstaller."""
    try:
        return version("flowtrack")
    except PackageNotFoundError:
        # An uninstalled checkout has no distribution metadata. Its pyproject is
        # the same authoritative metadata source used to build the distribution.
        project_file = Path(__file__).resolve().parents[2] / "pyproject.toml"
        try:
            project = tomllib.loads(project_file.read_text(encoding="utf-8"))["project"]
            return str(project["version"])
        except (OSError, KeyError, tomllib.TOMLDecodeError):
            return "0+unknown"
