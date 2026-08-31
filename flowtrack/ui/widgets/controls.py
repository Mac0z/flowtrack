"""Small reusable controls for the application shell."""

from PySide6.QtWidgets import QFrame, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class NavigationButton(QPushButton):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("navItem")
        self.setCheckable(True)
        self.setMinimumHeight(40)


class FlowButton(QPushButton):
    """General text/icon button styled by semantic application QSS."""


class CommandField(QLineEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Search or run a command…")
        self.setClearButtonEnabled(True)


class SurfaceCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")


class SectionHeading(QWidget):
    def __init__(self, title: str, description: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)
        if description:
            description_label = QLabel(description)
            description_label.setObjectName("secondaryText")
            layout.addWidget(description_label)
