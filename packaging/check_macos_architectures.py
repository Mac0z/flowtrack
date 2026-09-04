"""Fail early when a macOS packaging dependency contains a thin Mach-O file."""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

REQUIRED_ARCHITECTURES = frozenset({"x86_64", "arm64"})
RUNTIME_PACKAGES = (
    ("PySide6", "PySide6"),
    ("shiboken6", "shiboken6"),
    ("SQLAlchemy", "sqlalchemy"),
    ("MarkupSafe", "markupsafe"),
    ("Alembic", "alembic"),
    ("Mako", "mako"),
)
OPTIONAL_RUNTIME_PACKAGES = (("greenlet", "greenlet"),)


@dataclass(frozen=True)
class NativeFile:
    """The architecture inspection result for one candidate native file."""

    package: str
    path: Path
    architectures: frozenset[str]
    is_macho: bool

    @property
    def classification(self) -> str:
        if not self.is_macho:
            return "non-Mach-O / not applicable"
        if REQUIRED_ARCHITECTURES <= self.architectures:
            return "universal2"
        if self.architectures == {"arm64"}:
            return "arm64-only"
        if self.architectures == {"x86_64"}:
            return "x86_64-only"
        return "unsupported Mach-O architectures"


CommandRunner = Callable[[Sequence[str]], str]


def _run_command(command: Sequence[str]) -> str:
    return subprocess.run(
        command, check=True, capture_output=True, text=True
    ).stdout.strip()


def inspect_file(
    path: Path, package: str, *, run_command: CommandRunner = _run_command
) -> NativeFile:
    """Classify a possible native file using the macOS ``file`` and ``lipo`` tools."""
    description = run_command(("file", "-b", str(path)))
    if "Mach-O" not in description:
        return NativeFile(package, path, frozenset(), False)
    architectures = frozenset(run_command(("lipo", "-archs", str(path))).split())
    return NativeFile(package, path, architectures, True)


def candidate_files(root: Path) -> list[Path]:
    """Return extension and dynamic-library candidates below an installed package."""
    if root.is_file():
        return [root]
    # Qt frameworks have extensionless executable library files (for example,
    # ``QtCore.framework/Versions/A/QtCore``), so suffix matching alone is not
    # enough. ``file`` cheaply excludes executable scripts and data afterward.
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and (path.suffix in {".so", ".dylib"} or os.access(path, os.X_OK))
    )


def package_directory(module_name: str) -> Path:
    """Resolve an installed module without importing its optional native code."""
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        raise SystemExit(f"Required runtime package is not installed: {module_name}")
    if spec.submodule_search_locations:
        return Path(next(iter(spec.submodule_search_locations))).resolve()
    if spec.origin is None:
        raise SystemExit(f"Cannot locate runtime package: {module_name}")
    return Path(spec.origin).resolve().parent


def python_runtime_roots() -> list[Path]:
    """Locate the interpreter and native standard-library files PyInstaller may collect."""
    roots = [Path(sys.executable).resolve()]
    stdlib = Path(sysconfig.get_path("stdlib"))
    roots.append(stdlib / "lib-dynload")
    library = sysconfig.get_config_var("LDLIBRARY")
    library_dir = sysconfig.get_config_var("LIBDIR")
    if library and library_dir:
        roots.append(Path(library_dir) / library)
    return list(dict.fromkeys(root for root in roots if root.exists()))


def audit_roots(
    roots: Iterable[tuple[str, Path]], *, run_command: CommandRunner = _run_command
) -> tuple[dict[str, list[NativeFile]], list[NativeFile]]:
    """Inspect candidate files and return grouped results plus incompatible binaries."""
    results: dict[str, list[NativeFile]] = {}
    incompatible: list[NativeFile] = []
    for package, root in roots:
        package_results = [
            inspect_file(path, package, run_command=run_command)
            for path in candidate_files(root)
        ]
        results.setdefault(package, []).extend(package_results)
        incompatible.extend(
            result
            for result in package_results
            if result.is_macho
            and not REQUIRED_ARCHITECTURES <= result.architectures
        )
    return results, incompatible


def format_status(results: list[NativeFile]) -> str:
    """Summarise one package for readable CI output."""
    native = [result for result in results if result.is_macho]
    if not native:
        return "pure Python / OK"
    if all(REQUIRED_ARCHITECTURES <= result.architectures for result in native):
        return f"OK ({len(native)} universal2 native file(s))"
    return "FAILED"


def main(argv: Sequence[str] | None = None) -> int:
    """Audit the conservative set of runtime dependencies used by FlowTrack."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    if sys.platform != "darwin":
        raise SystemExit("This architecture preflight must run on macOS")

    roots = [(name, package_directory(module)) for name, module in RUNTIME_PACKAGES]
    installed_optional_names: list[str] = []
    for name, module in OPTIONAL_RUNTIME_PACKAGES:
        if importlib.util.find_spec(module) is not None:
            roots.append((name, package_directory(module)))
            installed_optional_names.append(name)
    roots.extend(("Python", root) for root in python_runtime_roots())
    results, incompatible = audit_roots(roots)

    print("macOS packaging architecture preflight")
    print()
    names = (
        "Python",
        *(name for name, _module in RUNTIME_PACKAGES),
        *installed_optional_names,
    )
    for name in names:
        print(f"{name + ':':<18}{format_status(results.get(name, []))}")

    inspected = sum(result.is_macho for group in results.values() for result in group)
    overall = "FAILED" if incompatible else "OK"
    print(f"Other binaries:   {overall} ({inspected} scoped Mach-O file(s) inspected)")
    if incompatible:
        print("\nIncompatible runtime binaries:", file=sys.stderr)
        for result in incompatible:
            architectures = " ".join(sorted(result.architectures)) or "unknown"
            print(
                f"- package={result.package} path={result.path} "
                f"architectures={architectures} classification={result.classification}",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
