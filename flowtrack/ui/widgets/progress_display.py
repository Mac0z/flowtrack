"""Reusable presentation for an already-calculated progress percentage."""

from PySide6.QtWidgets import QProgressBar


class ProgressDisplay(QProgressBar):
    """A compact, display-only progress bar with its percentage visible."""

    def __init__(self, percentage: float = 0, parent=None) -> None:
        super().__init__(parent)
        self.setRange(0, 100)
        self.setTextVisible(True)
        self.setMaximumHeight(18)
        self.set_percentage(percentage)

    def set_percentage(self, percentage: float) -> None:
        self.setValue(round(max(0.0, min(100.0, percentage))))
