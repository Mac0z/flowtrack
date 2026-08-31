"""Minimal M0 main window."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow


class MainWindow(QMainWindow):
    """The placeholder application window; feature navigation begins in M3."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FlowTrack")
        self.resize(960, 640)

        placeholder = QLabel("FlowTrack")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(placeholder)

