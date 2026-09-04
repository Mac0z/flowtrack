# M9B native packaging

FlowTrack uses **PyInstaller 6.16.0**, pinned in the `packaging` optional
dependency group. It is a build dependency, not an application runtime
dependency. The checked-in spec produces an **onedir** application because that
keeps Qt deployment inspectable, avoids temporary onefile extraction, starts
faster, and makes missing-plugin diagnosis clearer.

## Build and output

Install Python 3.12 and the native dependencies, then run from any directory:

```console
python -m pip install -e ".[dev,packaging]"
python packaging/build.py
```

The script rejects non-3.12 and non-release platforms, removes only
`build/pyinstaller` and the existing platform-specific FlowTrack artifact, and
reports its result. Builds must be native; Linux is not a packaging target.

* Windows 10/11 x86-64: `dist/FlowTrack/FlowTrack.exe` and its onedir runtime.
  The executable is a GUI/no-console executable. Its Product name and File
  description are FlowTrack, and version fields are generated at build time
  from installed project metadata.
* macOS 11+: `dist/FlowTrack.app`, bundle identifier `com.flowtrack.app`.
  `argv_emulation` is disabled. `MACOSX_DEPLOYMENT_TARGET=11.0` and
  `LSMinimumSystemVersion=11.0` are set.

There is no approved icon in the repository, so M9B intentionally uses the
PyInstaller default. The spec keeps icon selection in one place for a future
`.icns`/`.ico`. CI output is unsigned/ad-hoc as PyInstaller requires; Developer
ID signing, notarisation, Windows signing, installers, and a final icon remain
release/M9C work.

## Frozen resources and data safety

The spec bundles FlowTrack distribution metadata and the complete Alembic tree,
including `env.py`, revision modules, and `script.py.mako`. Runtime resource
discovery is centralised in `flowtrack.infrastructure.resources`; Alembic still
runs normally and is never bypassed. The version comes from bundled installed
metadata, not Git or a second maintained string, so leases remain meaningful.

Datasets, local locks, QSettings, and logs retain their existing external,
per-user paths. They do not derive from `sys.executable`, `_MEIPASS`, the source
directory, the app bundle, or the Windows distribution directory. The internal
smoke check uses an automatically deleted temporary dataset.

Set `FLOWTRACK_PACKAGING_SMOKE_TEST=1` only in packaging validation. FlowTrack
then checks Qt, SQLAlchemy, Alembic, version metadata and migration resources;
creates and migrates a temporary SQLite dataset; checks migration head and
integrity; closes it; and exits before the GUI event loop. With
`FLOWTRACK_PACKAGING_GUI_SMOKE_TEST=1`, it instead opens a temporary dataset,
shows the real main window, and exits automatically after one second. Neither
variable changes ordinary startup.

## CI and architecture validation

`.github/workflows/package.yml` has independent native Windows and macOS jobs.
The Windows job uses Windows Server 2022, Python 3.12 x64, validates both smoke
modes, inspects `FlowTrack.exe`, and uploads `FlowTrack-Windows-x64`.

The macOS job uses the standard `macos-14` runner. It records the actual
runner architecture with
`uname -m` for diagnostics, but never treats that architecture as evidence
about the application. The build continues to install the pinned official
Python.org 3.12.10 universal2 framework and uses
`/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`. Before the
build, CI records that interpreter with `file` and requires `lipo -archs` to
report both **x86_64 and arm64**.

For this macOS packaging job only, pip builds SQLAlchemy from its source
distribution with SQLAlchemy's supported `DISABLE_SQLALCHEMY_CEXT=1` switch.
`--no-binary SQLAlchemy` is required as well so pip does not select a
runner-architecture wheel before that source-build switch can take effect. This
keeps the application's existing `SQLAlchemy>=2.0,<2.1` version range while
intentionally using SQLAlchemy's pure-Python runtime and avoiding optional
`sqlalchemy/cyextension/*.so` files whose single-architecture Mach-O slices
prevent universal2 collection. CI imports SQLAlchemy, reports its resolved
version and package path, lists matching native extensions, and fails before
PyInstaller if any are present.

This packaging choice does not change application or persistence semantics and
does not affect normal development installations. The Windows job remains
unchanged and may use SQLAlchemy's compiled extensions from its normal wheel.

The PyInstaller spec requests `target_arch="universal2"`, and CI accepts and
names `FlowTrack-macOS-universal2` only after `lipo -archs` finds **both x86_64
and arm64** in the final `FlowTrack.app/Contents/MacOS/FlowTrack` executable.
In addition to PyInstaller's collected-binary architecture validation, CI finds
and applies the same explicit two-slice check to the bundled Python runtime and
Qt Core library. It also records `file`, Mach-O `LC_BUILD_VERSION`, and the full
`Info.plist` output. `MACOSX_DEPLOYMENT_TARGET=11.0` remains set for the build,
and the bundle declares `LSMinimumSystemVersion=11.0`. The app is zipped with
`ditto` to preserve bundle links.

A successful macOS 14 build and deployment metadata inspection do **not** prove
runtime compatibility with Big Sur. Clean-machine Intel/Apple Silicon and
actual macOS 11 runtime validation belong to M9C.

## Warning review and remaining validation

PyInstaller warnings remain visible in both job logs and are not globally
suppressed. Hooks may report optional/platform-specific modules from SQLAlchemy,
Alembic, Qt, or PyInstaller itself; these are acceptable only when the bundled
smoke checks still prove the required imports, Qt platform loading, migrations,
and database integrity. Any missing FlowTrack migration, Qt platform plugin,
SQLite support, or required import is a packaging failure.

This Linux development environment cannot produce or inspect native M9B
artifacts. The native workflow is the reproducible validation authority. M9C
must still cover clean machines, macOS 11 on Intel and Apple Silicon, Windows
10/11 x64, Gatekeeper/SmartScreen distribution behaviour, final signing and
notarisation choices, the final icon, and cross-platform dataset transfer.
