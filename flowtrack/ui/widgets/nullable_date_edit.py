"""Explicit nullable calendar-date editor shared by task surfaces."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QContextMenuEvent, QKeyEvent
from PySide6.QtWidgets import QDateEdit


class NullableDateEdit(QDateEdit):
    """A date editor with an explicit unset state, independent of Qt sentinels."""

    def __init__(self, none_text: str = "None", parent=None) -> None:
        super().__init__(parent)
        self._none_text = none_text
        self._is_none = False
        self._setting_value = False
        self.setCalendarPopup(True)
        self.dateChanged.connect(self._date_changed)
        calendar = self.calendarWidget()
        if calendar is not None:
            calendar.clicked.connect(self._calendar_date_selected)
        self.set_date_or_none(None)

    def set_date_or_none(self, value: date | None) -> None:
        self._setting_value = True
        self._is_none = value is None
        display_value = value or date.today()
        self.setDate(QDate(display_value.year, display_value.month, display_value.day))
        self._setting_value = False
        self.lineEdit().setText(self._none_text if self._is_none else self.textFromDate(self.date()))

    def date_or_none(self) -> date | None:
        if self._is_none:
            return None
        value = self.date()
        return date(value.year(), value.month(), value.day())

    def clear_date(self) -> None:
        """Put the editor into its intentional unset state."""
        self.set_date_or_none(None)

    def _date_changed(self, _value: QDate) -> None:
        if not self._setting_value:
            self._is_none = False

    def _calendar_date_selected(self, value: QDate) -> None:
        self._is_none = False
        self.setDate(value)

    def textFromDate(self, value: QDate) -> str:
        if getattr(self, "_is_none", False):
            return self._none_text
        return super().textFromDate(value)

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
