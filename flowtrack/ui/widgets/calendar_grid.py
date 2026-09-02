"""Qt-native month and week grids for task planning."""
from __future__ import annotations

import calendar
from collections.abc import Callable
from datetime import date, timedelta
from enum import StrEnum
from uuid import UUID

from PySide6.QtCore import QByteArray, QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QAbstractItemView, QFrame, QGridLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from flowtrack.application.task_queries import TaskRow
from flowtrack.domain.enums import TaskPriority, TaskStatus
from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.ui.theme import get_theme
from flowtrack.ui.theme.status import status_color

TASK_DATE_MIME_TYPE = "application/x-flowtrack-calendar-task"


class CalendarMode(StrEnum):
    MONTH = "month"
    WEEK = "week"


def month_start(value: date) -> date:
    return value.replace(day=1)


def week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


class CalendarTaskList(QListWidget):
    """Compact task list that sends cross-date drops to the view controller."""

    task_activated = Signal(object)

    def __init__(self, target_date: date | None, move_task: Callable[[UUID, date], bool], parent=None) -> None:
        super().__init__(parent)
        self.target_date = target_date
        self._move_task = move_task
        self.setObjectName("calendarTaskList")
        self.setDragEnabled(True)
        self.setAcceptDrops(target_date is not None)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSpacing(3)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.itemClicked.connect(lambda item: self.task_activated.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.itemDoubleClicked.connect(lambda item: self.task_activated.emit(item.data(Qt.ItemDataRole.UserRole)))

    def startDrag(self, _actions: Qt.DropAction) -> None:
        item = self.currentItem()
        if item is None:
            return
        mime = QMimeData()
        mime.setData(TASK_DATE_MIME_TYPE, QByteArray(str(item.data(Qt.ItemDataRole.UserRole)).encode("ascii")))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self.viewport().grab(self.visualItemRect(item)))
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event) -> None:
        event.acceptProposedAction() if event.mimeData().hasFormat(TASK_DATE_MIME_TYPE) else event.ignore()

    def dragMoveEvent(self, event) -> None:
        event.acceptProposedAction() if event.mimeData().hasFormat(TASK_DATE_MIME_TYPE) else event.ignore()

    def dropEvent(self, event) -> None:
        if self.target_date is None or not event.mimeData().hasFormat(TASK_DATE_MIME_TYPE):
            event.ignore()
            return
        try:
            task_id = UUID(bytes(event.mimeData().data(TASK_DATE_MIME_TYPE)).decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            event.ignore()
            return
        if self._move_task(task_id, self.target_date):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()


def _priority_marker(priority: TaskPriority) -> str:
    return "!" if priority in (TaskPriority.HIGH, TaskPriority.CRITICAL) else ""


class CalendarTaskChip(QFrame):
    """Semantic, compact rendering of one task read model."""

    def __init__(self, task: TaskRow, *, roomy: bool, parent=None) -> None:
        super().__init__(parent)
        theme = get_theme(ApplicationSettings().theme_id)
        self.setObjectName("calendarTaskChip")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 4, 7, 4)
        layout.setSpacing(1)
        title = QLabel(f"{_priority_marker(task.priority)}{task.title}")
        title.setToolTip(task.title)
        layout.addWidget(title)
        context = " · ".join(value for value in (task.project_name, task.owner_name if roomy else None) if value)
        if context:
            metadata = QLabel(context)
            metadata.setObjectName("mutedText")
            layout.addWidget(metadata)
        foreground = theme.colors.text_muted if task.status in (TaskStatus.COMPLETE, TaskStatus.CANCELLED) else theme.colors.text_primary
        border = theme.colors.danger if task.overdue else status_color(theme, task.status)
        self.setStyleSheet(
            f"QFrame#calendarTaskChip {{ background: {theme.colors.surface_secondary}; "
            f"border: 1px solid {theme.colors.border_subtle}; border-left: 3px solid {border}; "
            f"border-radius: {theme.radii.sm}px; color: {foreground}; }}"
        )


class CalendarGrid(QWidget):
    """Normal seven-column calendar grid, independent of persistence."""

    task_activated = Signal(object)

    def __init__(self, move_task: Callable[[UUID, date], bool], parent=None) -> None:
        super().__init__(parent)
        self._move_task = move_task
        self.mode = CalendarMode.MONTH
        self.anchor = month_start(date.today())
        self.cells: dict[date, CalendarTaskList] = {}
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(1)

    def render(self, rows: list[TaskRow], *, anchor: date, mode: CalendarMode, today: date | None = None) -> None:
        self.anchor, self.mode = anchor, mode
        today = today or date.today()
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cells.clear()
        first = week_start(month_start(anchor)) if mode is CalendarMode.MONTH else week_start(anchor)
        weeks = 6 if mode is CalendarMode.MONTH else 1
        by_date: dict[date, list[TaskRow]] = {}
        for row in rows:
            if row.due_date is not None:
                by_date.setdefault(row.due_date, []).append(row)
        theme = get_theme(ApplicationSettings().theme_id)
        for column, name in enumerate(calendar.day_abbr):
            heading = QLabel(name.upper())
            heading.setObjectName("mutedText")
            heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout.addWidget(heading, 0, column)
        for offset in range(weeks * 7):
            cell_date = first + timedelta(days=offset)
            frame = QFrame()
            frame.setObjectName("calendarDayCell")
            current_month = cell_date.month == anchor.month
            background = theme.colors.surface_primary if current_month or mode is CalendarMode.WEEK else theme.colors.application_background
            border = theme.colors.accent if cell_date == today else theme.colors.border_subtle
            frame.setStyleSheet(f"QFrame#calendarDayCell {{ background: {background}; border: 1px solid {border}; border-radius: {theme.radii.sm}px; }}")
            cell_layout = QVBoxLayout(frame)
            cell_layout.setContentsMargins(5, 4, 5, 4)
            cell_layout.setSpacing(3)
            date_label = QLabel(str(cell_date.day) if mode is CalendarMode.MONTH else cell_date.strftime("%d %b"))
            date_label.setStyleSheet(f"font-weight: {theme.typography.weight_semibold}; color: {theme.colors.accent if cell_date == today else (theme.colors.text_primary if current_month else theme.colors.text_muted)};")
            cell_layout.addWidget(date_label)
            task_list = CalendarTaskList(cell_date, self._move_task)
            task_list.task_activated.connect(self.task_activated)
            visible = by_date.get(cell_date, [])
            limit = 3 if mode is CalendarMode.MONTH else len(visible)
            for task in visible[:limit]:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, task.id)
                item.setSizeHint(QSize(0, 40 if mode is CalendarMode.MONTH else 58))
                task_list.addItem(item)
                task_list.setItemWidget(item, CalendarTaskChip(task, roomy=mode is CalendarMode.WEEK))
            if len(visible) > limit:
                more = QListWidgetItem(f"+{len(visible) - limit} more")
                more.setFlags(Qt.ItemFlag.ItemIsEnabled)
                task_list.addItem(more)
            cell_layout.addWidget(task_list, 1)
            self.cells[cell_date] = task_list
            self._layout.addWidget(frame, 1 + offset // 7, offset % 7)
        for column in range(7):
            self._layout.setColumnStretch(column, 1)
        for row in range(1, weeks + 1):
            self._layout.setRowStretch(row, 1)
