"""Cross-platform persistence for UI-only application preferences."""
import json

from PySide6.QtCore import QByteArray, QSettings

from flowtrack.ui.theme import DEFAULT_THEME_ID, get_theme


class ApplicationSettings:
    """Typed facade over QSettings; business data never belongs here."""

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings()

    @property
    def theme_id(self) -> str:
        value = self._settings.value("appearance/theme", DEFAULT_THEME_ID, type=str)
        return get_theme(value).identifier

    @theme_id.setter
    def theme_id(self, identifier: str) -> None:
        self._settings.setValue("appearance/theme", get_theme(identifier).identifier)
        self._settings.sync()

    @property
    def last_destination(self) -> str:
        return self._settings.value("shell/last_destination", "dashboard", type=str)

    @last_destination.setter
    def last_destination(self, destination: str) -> None:
        self._settings.setValue("shell/last_destination", destination)

    def window_geometry(self) -> QByteArray:
        return self._settings.value("window/geometry", QByteArray(), type=QByteArray)

    def window_state(self) -> QByteArray:
        return self._settings.value("window/state", QByteArray(), type=QByteArray)

    def save_window(self, geometry: QByteArray, state: QByteArray) -> None:
        self._settings.setValue("window/geometry", geometry)
        self._settings.setValue("window/state", state)
        self._settings.sync()

    @property
    def my_tasks_filters(self) -> dict[str, object]:
        """Return JSON-safe My Tasks preferences (never business data)."""
        raw = self._settings.value("my_tasks/filters", "{}", type=str)
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except (TypeError, json.JSONDecodeError):
            return {}

    @my_tasks_filters.setter
    def my_tasks_filters(self, filters: dict[str, object]) -> None:
        self._settings.setValue("my_tasks/filters", json.dumps(filters, sort_keys=True))
        self._settings.sync()
