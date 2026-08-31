"""Theme registry and application helpers."""

from PySide6.QtWidgets import QApplication

from flowtrack.ui.theme.dark import DARK_THEME
from flowtrack.ui.theme.stylesheet import build_stylesheet
from flowtrack.ui.theme.tokens import Theme

DEFAULT_THEME_ID = "dark"
BUILTIN_THEMES: dict[str, Theme] = {DARK_THEME.identifier: DARK_THEME}


def get_theme(identifier: str | None) -> Theme:
    """Return a built-in theme, safely falling back to Dark."""
    return BUILTIN_THEMES.get(identifier or DEFAULT_THEME_ID, DARK_THEME)


def apply_theme(application: QApplication, theme: Theme) -> None:
    """Apply one centrally generated stylesheet to the application."""
    application.setStyleSheet(build_stylesheet(theme))


__all__ = ["BUILTIN_THEMES", "DARK_THEME", "DEFAULT_THEME_ID", "Theme", "apply_theme", "get_theme"]
