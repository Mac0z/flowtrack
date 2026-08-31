"""Central definitions for platform-aware shell shortcuts."""

from dataclasses import dataclass

from PySide6.QtGui import QKeySequence


@dataclass(frozen=True, slots=True)
class ShellShortcuts:
    """Qt portable sequences map Ctrl to Command on macOS automatically."""

    quick_task: QKeySequence
    command_palette: QKeySequence
    active_view_search: QKeySequence


def shell_shortcuts() -> ShellShortcuts:
    return ShellShortcuts(
        quick_task=QKeySequence(QKeySequence.StandardKey.New),
        command_palette=QKeySequence("Ctrl+K", QKeySequence.SequenceFormat.PortableText),
        active_view_search=QKeySequence(QKeySequence.StandardKey.Find),
    )
