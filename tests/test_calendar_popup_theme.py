"""Focused coverage for the central date-popup theme."""

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCalendarWidget

from flowtrack.ui.theme import apply_theme
from flowtrack.ui.theme.dark import DARK_THEME
from flowtrack.ui.theme.stylesheet import build_stylesheet


def test_stylesheet_uses_theme_tokens_for_calendar_popup() -> None:
    stylesheet = build_stylesheet(DARK_THEME)
    colors = DARK_THEME.colors

    assert "QCalendarWidget QWidget#qt_calendar_navigationbar" in stylesheet
    assert "QCalendarWidget QToolButton:hover" in stylesheet
    assert "QCalendarWidget QAbstractItemView" in stylesheet
    assert f"background: {colors.surface_primary}" in stylesheet
    assert f"alternate-background-color: {colors.surface_secondary}" in stylesheet
    assert f"selection-background-color: {colors.accent}" in stylesheet
    assert f"border: 1px solid {colors.focus}" in stylesheet
    assert f"color: {colors.disabled}" in stylesheet


def test_application_theme_semantically_colours_calendar_weekdays(application) -> None:
    apply_theme(application, DARK_THEME)
    calendar = QCalendarWidget()
    calendar.ensurePolished()

    weekday = calendar.weekdayTextFormat(Qt.DayOfWeek.Monday).foreground().color()
    weekend = calendar.weekdayTextFormat(Qt.DayOfWeek.Saturday).foreground().color()
    today = calendar.dateTextFormat(QDate.currentDate()).foreground().color()

    assert weekday == QColor(DARK_THEME.colors.text_secondary)
    assert weekend == QColor(DARK_THEME.colors.danger)
    assert today == QColor(DARK_THEME.colors.accent)
