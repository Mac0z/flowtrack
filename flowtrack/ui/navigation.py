"""Stable navigation destinations and state."""

from dataclasses import dataclass
from enum import StrEnum

from PySide6.QtCore import QObject, Signal


class Destination(StrEnum):
    DASHBOARD = "dashboard"
    MY_TASKS = "my_tasks"
    PROJECTS = "projects"
    CALENDAR = "calendar"
    TIMELINE = "timeline"
    REPORTS = "reports"
    SETTINGS = "settings"


@dataclass(frozen=True, slots=True)
class NavigationItem:
    destination: Destination
    label: str


PRIMARY_NAVIGATION = (
    NavigationItem(Destination.DASHBOARD, "Dashboard"), NavigationItem(Destination.MY_TASKS, "My Tasks"),
    NavigationItem(Destination.PROJECTS, "Projects"), NavigationItem(Destination.CALENDAR, "Calendar"),
    NavigationItem(Destination.TIMELINE, "Timeline"), NavigationItem(Destination.REPORTS, "Reports"),
    NavigationItem(Destination.SETTINGS, "Settings"),
)


class NavigationController(QObject):
    """Owns active destination independently of page construction."""

    destination_changed = Signal(object)

    def __init__(self, initial: Destination = Destination.DASHBOARD) -> None:
        super().__init__()
        self._destination = initial

    @property
    def destination(self) -> Destination:
        return self._destination

    def navigate(self, destination: Destination) -> None:
        if destination != self._destination:
            self._destination = destination
            self.destination_changed.emit(destination)
