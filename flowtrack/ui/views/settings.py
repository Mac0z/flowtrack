"""Minimal data-location settings display for M8A."""

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class SettingsView(QWidget):
    def __init__(self, data_directory: Path) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel("Data"))
        location = QLabel(str(data_directory))
        location.setTextInteractionFlags(location.textInteractionFlags())
        location.setObjectName("mutedText")
        layout.addWidget(location)
        open_folder = QPushButton("Open Data Folder")
        open_folder.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_directory)))
        )
        layout.addWidget(open_folder)
        layout.addStretch()
