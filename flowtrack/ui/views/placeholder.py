"""Polished milestone placeholders for future feature views."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from flowtrack.ui.widgets import SectionHeading, SurfaceCard


class PlaceholderView(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 34, 40, 40)
        layout.setSpacing(24)
        layout.addWidget(SectionHeading(title, "FlowTrack workspace"))
        card = SurfaceCard()
        card.setMinimumHeight(180)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        message = QLabel(f"{title} is ready for a future milestone.")
        message.setObjectName("secondaryText")
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(message)
        layout.addWidget(card)
        layout.addStretch()
