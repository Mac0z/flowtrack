"""Keyboard-first global command/search shell."""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from flowtrack.ui.widgets import CommandField


class CommandPalette(QDialog):
    command_triggered = Signal(str)
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Command Palette")
        self.setModal(True)
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        self.command_field = CommandField()
        self.command_field.setAccessibleName("Command search")
        layout.addWidget(self.command_field)
        self.commands = QListWidget()
        for text in ("Quick Task", "Go to Dashboard", "Go to My Tasks", "Go to Projects", "Open Settings"):
            self.commands.addItem(QListWidgetItem(text))
        self.commands.setCurrentRow(0)
        layout.addWidget(self.commands)
        hint = QLabel("Type to filter commands  ·  ↑↓ to navigate  ·  Esc to close")
        hint.setObjectName("mutedText")
        layout.addWidget(hint)
        self.command_field.textChanged.connect(self._filter)
        self.command_field.returnPressed.connect(self._activate)
        self.commands.itemActivated.connect(lambda _item: self._activate())
        self.command_field.installEventFilter(self)

    def open(self) -> None:
        self.command_field.clear()
        super().open()
        self.command_field.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _filter(self, query: str) -> None:
        first_visible = -1
        for row in range(self.commands.count()):
            item = self.commands.item(row)
            item.setHidden(query.casefold() not in item.text().casefold())
            if not item.isHidden() and first_visible < 0:
                first_visible = row
        self.commands.setCurrentRow(first_visible)

    def _activate(self) -> None:
        item = self.commands.currentItem()
        if item is not None and not item.isHidden():
            self.command_triggered.emit(item.text())
            self.accept()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self.command_field and event.type() == QEvent.Type.KeyPress:
            key_event = event if isinstance(event, QKeyEvent) else None
            if key_event and key_event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self.commands.setFocus(Qt.FocusReason.TabFocusReason)
                offset = 1 if key_event.key() == Qt.Key.Key_Down else -1
                row = max(0, min(self.commands.count() - 1, self.commands.currentRow() + offset))
                self.commands.setCurrentRow(row)
                return True
        return super().eventFilter(watched, event)
