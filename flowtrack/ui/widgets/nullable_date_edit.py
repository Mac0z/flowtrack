"""Explicit nullable calendar-date editor shared by task surfaces."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QContextMenuEvent, QKeyEvent
from PySide6.QtWidgets import QDateEdit


class NullableDateEdit(QDateEdit):
    """A QDateEdit whose minimum value is deliberately represented as unset."""

    def __init__(self, none_text: str = "None", parent=None) -> None:
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setSpecialValueText(none_text)
        self.set_date_or_none(None)

    def set_date_or_none(self, value: date | None) -> None:
        self.setDate(QDate(value.year, value.month, value.day) if value else self.minimumDate())

    def date_or_none(self) -> date | None:
        if self.date() == self.minimumDate():
            return None
        value = self.date()
        return date(value.year(), value.month(), value.day())

    def clear_date(self) -> None:
        """Put the editor into its intentional unset state."""
        self.set_date_or_none(None)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Delete:
            self.clear_date()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = self.lineEdit().createStandardContextMenu()
        menu.addSeparator()
        menu.addAction("Clear date", self.clear_date)
        menu.exec(event.globalPos())
