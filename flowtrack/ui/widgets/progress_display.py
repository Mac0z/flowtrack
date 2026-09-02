"""Reusable presentation for an already-calculated progress percentage."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QProgressBar, QWidget


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


class ProgressCell(QWidget):
    """Transparent table-cell host that vertically centres compact progress."""

    def __init__(self, percentage: float = 0, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAutoFillBackground(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(0)
        self.progress_display = ProgressDisplay(percentage, self)
        layout.addWidget(
            self.progress_display,
            1,
            Qt.AlignmentFlag.AlignVCenter,
        )
