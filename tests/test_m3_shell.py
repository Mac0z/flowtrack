import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence

from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.ui.navigation import Destination, PRIMARY_NAVIGATION
from flowtrack.ui.shortcuts import shell_shortcuts
from flowtrack.ui.theme import DARK_THEME, get_theme
from flowtrack.ui.theme.tokens import ColorTokens
from flowtrack.ui.widgets import CommandField, FlowButton, NavigationButton, SectionHeading, SurfaceCard
from flowtrack.ui.windows.main_window import MainWindow


@pytest.fixture
def settings(tmp_path):
    store = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    return ApplicationSettings(store)


def test_dark_theme_has_every_required_semantic_token() -> None:
    assert DARK_THEME.identifier == "dark"
    assert get_theme("missing") is DARK_THEME
    for token in ColorTokens.__dataclass_fields__:
        assert getattr(DARK_THEME.colors, token)


def test_settings_persists_theme_and_falls_back(settings: ApplicationSettings) -> None:
    assert settings.theme_id == "dark"
    settings.theme_id = "dark"
    assert settings.theme_id == "dark"
    settings._settings.setValue("appearance/theme", "unknown")
    assert settings.theme_id == "dark"


def test_shell_contains_and_navigates_all_destinations(application, settings) -> None:
    window = MainWindow(settings)
    assert tuple(window.pages) == tuple(item.destination for item in PRIMARY_NAVIGATION)
    for item in PRIMARY_NAVIGATION:
        window.navigate(item.destination)
        assert window.active_destination is item.destination
        assert window.page_stack.currentWidget() is window.pages[item.destination]
        assert window.navigation_buttons[item.destination].isChecked()
    window.close()


def test_window_preferences_are_saved(application, settings) -> None:
    window = MainWindow(settings)
    window.resize(1100, 700)
    window.close()
    assert not settings.window_geometry().isEmpty()


def test_command_palette_opens_and_closes(application, settings) -> None:
    window = MainWindow(settings)
    window.open_command_palette()
    assert window.command_palette.isVisible()
    window.command_palette.reject()
    assert not window.command_palette.isVisible()
    window.close()


def test_shortcut_definitions_use_qt_portable_sequences() -> None:
    shortcuts = shell_shortcuts()
    assert shortcuts.quick_task.matches(QKeySequence(QKeySequence.StandardKey.New)) == QKeySequence.SequenceMatch.ExactMatch
    assert shortcuts.active_view_search.matches(QKeySequence(QKeySequence.StandardKey.Find)) == QKeySequence.SequenceMatch.ExactMatch
    assert shortcuts.command_palette.toString(QKeySequence.SequenceFormat.PortableText) == "Ctrl+K"


def test_reusable_controls_instantiate(application) -> None:
    controls = [NavigationButton("Nav"), FlowButton("Action"), CommandField(), SurfaceCard(), SectionHeading("Title")]
    assert all(control is not None for control in controls)
