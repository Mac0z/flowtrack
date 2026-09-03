"""PyInstaller onedir configuration for native FlowTrack builds."""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
WINDOWS_VERSION = ROOT / "packaging" / ".pyinstaller" / "windows-version.txt"
TARGET_ARCH = "universal2" if sys.platform == "darwin" else None

datas = copy_metadata("flowtrack")
datas += collect_data_files("flowtrack.persistence.migrations", include_py_files=True)

analysis = Analysis(
    [str(ROOT / "flowtrack" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=(
        collect_submodules("alembic")
        + collect_submodules("sqlalchemy.dialects.sqlite")
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="FlowTrack",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=TARGET_ARCH,
    version=str(WINDOWS_VERSION) if sys.platform == "win32" else None,
    argv_emulation=False,
)
distribution = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="FlowTrack",
)

if sys.platform == "darwin":
    application = BUNDLE(
        distribution,
        name="FlowTrack.app",
        icon=None,
        bundle_identifier="com.flowtrack.app",
        version=os.environ.get("FLOWTRACK_BUILD_VERSION", "0+unknown"),
        info_plist={"LSMinimumSystemVersion": "11.0"},
        target_arch="universal2",
    )
