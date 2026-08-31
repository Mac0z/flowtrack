# FlowTrack

FlowTrack is a local-first, cross-platform desktop task and project manager. This
repository currently contains the **M0 skeleton only**: a minimal Qt window,
diagnostic logging, platform/path abstractions, tests, and CI. No database or
task-management functionality has been implemented yet.

## Development setup

Use Python 3.12. FlowTrack does not support other Python feature releases. The
Qt API baseline is pinned to PySide6 6.7.3.

```console
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
python -m flowtrack
```

FlowTrack writes rotating diagnostic logs beneath the operating system's normal
per-user application-data location. The application does not create a database
in M0.

## Compatibility assumptions

- macOS 11 Big Sur or newer is supported on Intel and Apple Silicon.
- Windows 10 and 11 x86-64 are supported.
- Release artifacts must be built and smoke-tested on their target OS; they are
  not cross-built.
- Paths are represented with `pathlib.Path`. macOS uses
  `~/Library/Application Support/FlowTrack`; Windows uses `LOCALAPPDATA` (with
  the user's home as a safe fallback). No OneDrive location is assumed.
- Linux is supported only as a development/CI host and follows XDG conventions;
  it is not a product release target.
- Python 3.12 is the sole supported Python feature release, with PySide6 6.7.3
  pinned as the required Qt API baseline.
