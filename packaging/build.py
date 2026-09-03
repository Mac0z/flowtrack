"""Repeatable native PyInstaller build for FlowTrack."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "build" / "pyinstaller"
DIST_ROOT = ROOT / "dist"
GENERATED_ROOT = ROOT / "packaging" / ".pyinstaller"


def _flowtrack_version() -> str:
    try:
        return version("flowtrack")
    except PackageNotFoundError as error:
        raise SystemExit("FlowTrack must be installed before packaging: pip install -e .") from error


def _windows_version_file(value: str) -> Path:
    numeric = [int(part) for part in value.split("+")[0].split(".")]
    if len(numeric) > 4 or not numeric:
        raise SystemExit(f"FlowTrack version {value!r} cannot be used as Windows metadata")
    numeric.extend([0] * (4 - len(numeric)))
    dotted = ".".join(str(item) for item in numeric)
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    destination = GENERATED_ROOT / "windows-version.txt"
    destination.write_text(
        "VSVersionInfo(ffi=FixedFileInfo(filevers=%r, prodvers=%r, mask=0x3f, flags=0x0, "
        "OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)), kids=[StringFileInfo("
        "[StringTable('040904B0', [StringStruct('FileDescription', 'FlowTrack'), "
        "StringStruct('FileVersion', '%s'), StringStruct('ProductName', 'FlowTrack'), "
        "StringStruct('ProductVersion', '%s')])]), VarFileInfo([VarStruct('Translation', "
        "[1033, 1200])])])\n" % (tuple(numeric), tuple(numeric), dotted, value),
        encoding="utf-8",
    )
    return destination


def main() -> int:
    """Build only on supported native platforms and report the artifact."""
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("FlowTrack packaging requires Python 3.12")
    if importlib.util.find_spec("PyInstaller") is None:
        raise SystemExit('PyInstaller is missing; install with: pip install -e ".[packaging]"')
    system = platform.system()
    if system not in {"Darwin", "Windows"}:
        raise SystemExit("FlowTrack packages can only be built natively on macOS or Windows")

    app_version = _flowtrack_version()
    if system == "Windows":
        _windows_version_file(app_version)
    shutil.rmtree(BUILD_ROOT, ignore_errors=True)
    artifact = DIST_ROOT / ("FlowTrack.app" if system == "Darwin" else "FlowTrack")
    if artifact.exists():
        shutil.rmtree(artifact)
    environment = os.environ.copy()
    environment["FLOWTRACK_BUILD_VERSION"] = app_version
    if system == "Darwin":
        environment.setdefault("MACOSX_DEPLOYMENT_TARGET", "11.0")
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", str(DIST_ROOT), "--workpath", str(BUILD_ROOT),
        str(ROOT / "packaging" / "flowtrack.spec"),
    ]
    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    expected = artifact if system == "Darwin" else artifact / "FlowTrack.exe"
    if not expected.exists():
        raise SystemExit(f"PyInstaller completed without expected artifact: {expected}")
    print(f"FlowTrack {app_version} artifact: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
