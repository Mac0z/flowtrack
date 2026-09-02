"""Theme registry and application helpers."""

from PySide6.QtCore import QDate, QEvent, QObject, Qt
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import QApplication, QCalendarWidget

from flowtrack.ui.theme.dark import DARK_THEME
from flowtrack.ui.theme.stylesheet import build_stylesheet
from flowtrack.ui.theme.tokens import Theme

DEFAULT_THEME_ID = "dark"
BUILTIN_THEMES: dict[str, Theme] = {DARK_THEME.identifier: DARK_THEME}


class _CalendarThemePolisher(QObject):
    """Apply token colours that QCalendarWidget does not expose to QSS."""

    def __init__(self, theme: Theme, parent: QObject) -> None:
        super().__init__(parent)
        self._theme = theme

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(watched, QCalendarWidget) and event.type() in (
            QEvent.Type.Polish,
            QEvent.Type.Show,
        ):
            weekday_format = QTextCharFormat()
            weekday_format.setForeground(QColor(self._theme.colors.text_secondary))
            weekend_format = QTextCharFormat()
            weekend_format.setForeground(QColor(self._theme.colors.danger))
            today_format = QTextCharFormat()
            today_format.setForeground(QColor(self._theme.colors.accent))
            today_format.setFontWeight(self._theme.typography.weight_semibold)
            for day in (
                Qt.DayOfWeek.Monday,
                Qt.DayOfWeek.Tuesday,
                Qt.DayOfWeek.Wednesday,
                Qt.DayOfWeek.Thursday,
                Qt.DayOfWeek.Friday,
            ):
                watched.setWeekdayTextFormat(day, weekday_format)
            for day in (Qt.DayOfWeek.Saturday, Qt.DayOfWeek.Sunday):
                watched.setWeekdayTextFormat(day, weekend_format)
            watched.setDateTextFormat(QDate.currentDate(), today_format)
        return False


def get_theme(identifier: str | None) -> Theme:
    """Return a built-in theme, safely falling back to Dark."""
    return BUILTIN_THEMES.get(identifier or DEFAULT_THEME_ID, DARK_THEME)


def apply_theme(application: QApplication, theme: Theme) -> None:
    """Apply one centrally generated stylesheet to the application."""
    application.setStyleSheet(build_stylesheet(theme))
    previous_polisher = getattr(application, "_flowtrack_calendar_theme_polisher", None)
    if previous_polisher is not None:
        application.removeEventFilter(previous_polisher)
    polisher = _CalendarThemePolisher(theme, application)
    application.installEventFilter(polisher)
    application._flowtrack_calendar_theme_polisher = polisher


__all__ = ["BUILTIN_THEMES", "DARK_THEME", "DEFAULT_THEME_ID", "Theme", "apply_theme", "get_theme"]
