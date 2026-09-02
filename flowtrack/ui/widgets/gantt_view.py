"""Qt-native, read-only project Gantt with frozen task columns."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from uuid import UUID

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QButtonGroup, QFrame, QHeaderView,
    QHBoxLayout, QLabel, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from flowtrack.application.projects import ProjectQueryService, ProjectSummary
from flowtrack.application.task_queries import TaskRow
from flowtrack.domain.enums import TaskStatus
from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.ui.theme import get_theme
from flowtrack.ui.theme.status import status_color
from flowtrack.ui.widgets.gantt_timeline import (
    GanttZoom, TimelineRange, calculate_timeline_range, collapsed_descendant_dates,
    date_to_x, parent_ids, pixels_per_day, task_bar_geometry, visible_hierarchy,
)

ROW_HEIGHT = 38
HEADER_HEIGHT = 42
MILESTONE_SIZE = 7


def task_tooltip(task: TaskRow) -> str:
    parts = [task.title, f"Status: {task.status.value.replace('_', ' ').title()}",
             f"Start: {task.start_date.isoformat() if task.start_date else '—'}",
             f"Due: {task.due_date.isoformat() if task.due_date else '—'}",
             f"Progress: {task.progress:.0f}%"]
    if task.owner_name:
        parts.append(f"Owner: {task.owner_name}")
    return "\n".join(parts)


class GanttTimeline(QAbstractScrollArea):
    """One lightweight painting surface for all visible timeline rows."""
    task_activated = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.theme = get_theme(ApplicationSettings().theme_id)
        self.rows: list[TaskRow] = []
        self.zoom = GanttZoom.WEEK
        self.timeline_range = calculate_timeline_range((), zoom=self.zoom)
        self.has_dated_work = False
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.horizontalScrollBar().valueChanged.connect(self.viewport().update)
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)

    def set_rows(self, rows: list[TaskRow], timeline_range: TimelineRange, zoom: GanttZoom) -> None:
        self.rows, self.timeline_range, self.zoom = list(rows), timeline_range, zoom
        self.has_dated_work = any(row.start_date or row.due_date for row in rows)
        content_width = max(1, int(timeline_range.days * pixels_per_day(zoom)))
        self.horizontalScrollBar().setRange(0, max(0, content_width - self.viewport().width()))
        content_height = len(rows) * ROW_HEIGHT
        self.verticalScrollBar().setRange(0, max(0, content_height - (self.viewport().height() - HEADER_HEIGHT)))
        self.verticalScrollBar().setPageStep(max(ROW_HEIGHT, self.viewport().height() - HEADER_HEIGHT))
        self.viewport().update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.set_rows(self.rows, self.timeline_range, self.zoom)

    def _row_at(self, position: QPoint) -> TaskRow | None:
        if position.y() < HEADER_HEIGHT:
            return None
        index = (position.y() - HEADER_HEIGHT + self.verticalScrollBar().value()) // ROW_HEIGHT
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        task = self._row_at(event.position().toPoint())
        self.viewport().setToolTip(task_tooltip(task) if task and (task.start_date or task.due_date) else "")
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        task = self._row_at(event.position().toPoint())
        if task and event.button() == Qt.MouseButton.LeftButton:
            self.task_activated.emit(task.id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        task = self._row_at(event.position().toPoint())
        if task:
            self.task_activated.emit(task.id)
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self.viewport()); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = self.theme.colors; width = self.viewport().width(); height = self.viewport().height()
        painter.fillRect(self.viewport().rect(), QColor(colors.surface_primary))
        horizontal = self.horizontalScrollBar().value(); vertical = self.verticalScrollBar().value()
        painter.save(); painter.setClipRect(0, HEADER_HEIGHT, width, height - HEADER_HEIGHT)
        # Alternating rows and deterministic date separators.
        for index, task in enumerate(self.rows):
            y = HEADER_HEIGHT + index * ROW_HEIGHT - vertical
            if y + ROW_HEIGHT < HEADER_HEIGHT or y > height: continue
            if index % 2: painter.fillRect(0, y, width, ROW_HEIGHT, QColor(colors.surface_secondary))
            painter.setPen(QPen(QColor(colors.divider), 1)); painter.drawLine(0, y + ROW_HEIGHT - 1, width, y + ROW_HEIGHT - 1)
            geometry = task_bar_geometry(task, self.timeline_range, self.zoom)
            if geometry is None: continue
            x = geometry.x - horizontal
            bar_color = QColor(colors.danger if task.overdue else status_color(self.theme, task.status))
            if task.status in (TaskStatus.COMPLETE, TaskStatus.CANCELLED): bar_color.setAlpha(145)
            centre_y = y + ROW_HEIGHT / 2
            if geometry.milestone:
                diamond = QPolygonF([QPointF(x, centre_y-MILESTONE_SIZE), QPointF(x+MILESTONE_SIZE, centre_y), QPointF(x, centre_y+MILESTONE_SIZE), QPointF(x-MILESTONE_SIZE, centre_y)])
                painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(bar_color); painter.drawPolygon(diamond)
            else:
                rect = QRectF(x, centre_y - 8, geometry.width, 16)
                painter.setPen(QPen(bar_color.lighter(120), 1)); painter.setBrush(bar_color.darker(155)); painter.drawRoundedRect(rect, 4, 4)
                if geometry.progress_width:
                    path = QPainterPath(); path.addRoundedRect(QRectF(x, centre_y - 8, geometry.progress_width, 16), 4, 4)
                    painter.fillPath(path, bar_color)
        # Calendar grid and today marker are deliberately drawn over row backgrounds.
        step = {GanttZoom.DAY: 1, GanttZoom.WEEK: 7, GanttZoom.MONTH: 1}[self.zoom]
        cursor = self.timeline_range.start
        while cursor <= self.timeline_range.end:
            boundary = (self.zoom is GanttZoom.DAY or
                        self.zoom is GanttZoom.WEEK and cursor.weekday() == 0 or
                        self.zoom is GanttZoom.MONTH and cursor.day == 1)
            if boundary:
                x = date_to_x(cursor, self.timeline_range, self.zoom) - horizontal
                painter.setPen(QPen(QColor(colors.divider), 1)); painter.drawLine(int(x), HEADER_HEIGHT, int(x), height)
            cursor += timedelta(days=step)
        today_x = date_to_x(date.today(), self.timeline_range, self.zoom) - horizontal
        painter.setPen(QPen(QColor(colors.accent_hover), 2)); painter.drawLine(int(today_x), HEADER_HEIGHT, int(today_x), height)
        painter.restore()
        # Fixed header is painted last so neither scrollbar moves it vertically.
        painter.fillRect(0, 0, width, HEADER_HEIGHT, QColor(colors.surface_elevated))
        painter.setPen(QPen(QColor(colors.border_subtle), 1)); painter.drawLine(0, HEADER_HEIGHT-1, width, HEADER_HEIGHT-1)
        self._paint_header(painter, horizontal, width)
        if not self.has_dated_work:
            painter.setPen(QColor(colors.text_muted)); painter.drawText(QRectF(20, HEADER_HEIGHT+18, width-40, 50), Qt.AlignmentFlag.AlignHCenter, "Add start or due dates to see task bars on the timeline.")

    def _paint_header(self, painter: QPainter, horizontal: int, width: int) -> None:
        colors = self.theme.colors; cursor = self.timeline_range.start
        painter.setPen(QColor(colors.text_secondary))
        while cursor <= self.timeline_range.end:
            show = (self.zoom is GanttZoom.DAY or self.zoom is GanttZoom.WEEK and cursor.weekday() == 0 or self.zoom is GanttZoom.MONTH and cursor.day == 1)
            if show:
                x = date_to_x(cursor, self.timeline_range, self.zoom) - horizontal
                label = cursor.strftime("%a %d") if self.zoom is GanttZoom.DAY else (f"Week of {cursor.strftime('%d %b')}" if self.zoom is GanttZoom.WEEK else cursor.strftime("%B %Y"))
                painter.drawText(QRectF(x+6, 0, max(80, width), HEADER_HEIGHT), Qt.AlignmentFlag.AlignVCenter, label)
            cursor += timedelta(days=1)


class GanttView(QWidget):
    """Project-aware split view; task data remains immutable and query-backed."""
    task_activated = Signal(object)

    def __init__(self, queries: ProjectQueryService, parent=None) -> None:
        super().__init__(parent); self.queries = queries; self.project_id: UUID | None = None
        self.project: ProjectSummary | None = None; self.tasks: list[TaskRow] = []; self.visible_rows: list[TaskRow] = []
        self.collapsed: set[UUID] = set(); self.zoom = GanttZoom.WEEK; self._parents: set[UUID] = set()
        theme = get_theme(ApplicationSettings().theme_id)
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(9)
        toolbar = QHBoxLayout(); title = QLabel("Project timeline"); title.setStyleSheet(f"font-weight: {theme.typography.weight_semibold};")
        toolbar.addWidget(title); toolbar.addStretch(); toolbar.addWidget(QLabel("Zoom"))
        self.zoom_group = QButtonGroup(self); self.zoom_group.setExclusive(True); self.zoom_buttons: dict[GanttZoom,QPushButton] = {}
        for zoom in GanttZoom:
            button = QPushButton(zoom.value.title()); button.setCheckable(True); button.setProperty("compact", True)
            button.clicked.connect(lambda _checked=False, selected=zoom: self.set_zoom(selected)); self.zoom_group.addButton(button); toolbar.addWidget(button); self.zoom_buttons[zoom] = button
        self.zoom_buttons[self.zoom].setChecked(True); root.addLayout(toolbar)
        self.splitter = QSplitter(Qt.Orientation.Horizontal); self.splitter.setChildrenCollapsible(False)
        self.task_table = QTableWidget(0,2); self.task_table.setHorizontalHeaderLabels(["Task","Owner"]); self.task_table.verticalHeader().hide()
        self.task_table.horizontalHeader().setFixedHeight(HEADER_HEIGHT); self.task_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch); self.task_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Fixed); self.task_table.setColumnWidth(1,120)
        self.task_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.task_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); self.task_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel); self.task_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); self.task_table.setMinimumWidth(300)
        self.task_table.cellClicked.connect(self._cell_clicked); self.task_table.cellDoubleClicked.connect(self._activate_left)
        self.timeline = GanttTimeline(); self.timeline.task_activated.connect(self.task_activated)
        self.splitter.addWidget(self.task_table); self.splitter.addWidget(self.timeline); self.splitter.setSizes([390,700]); self.splitter.setStretchFactor(1,1); root.addWidget(self.splitter,1)
        left_scroll, right_scroll = self.task_table.verticalScrollBar(), self.timeline.verticalScrollBar()
        left_scroll.valueChanged.connect(right_scroll.setValue); right_scroll.valueChanged.connect(left_scroll.setValue)

    def set_project(self, project_id: UUID | None, project: ProjectSummary | None = None) -> None:
        self.project_id, self.project = project_id, project; self.collapsed.clear(); self.refresh()

    def refresh(self) -> None:
        self.tasks = self.queries.project_tasks(self.project_id) if self.project_id else []
        self._parents = parent_ids(self.tasks); self._rebuild()

    def set_zoom(self, zoom: GanttZoom | str) -> None:
        self.zoom = GanttZoom(zoom); self.zoom_buttons[self.zoom].setChecked(True); self._rebuild()

    def toggle_collapsed(self, task_id: UUID) -> None:
        if task_id not in self._parents: return
        self.collapsed.symmetric_difference_update({task_id}); self._rebuild()

    def _rebuild(self) -> None:
        self.visible_rows = visible_hierarchy(self.tasks, self.collapsed)
        display_rows = []
        for task in self.visible_rows:
            start, due = collapsed_descendant_dates(task, self.tasks) if task.id in self.collapsed else (task.start_date, task.due_date)
            display_rows.append(replace(task, start_date=start, due_date=due))
        self.task_table.setRowCount(len(self.visible_rows))
        for index, task in enumerate(self.visible_rows):
            marker = ("▸ " if task.id in self.collapsed else "▾ ") if task.id in self._parents else "  "
            name = QTableWidgetItem("    " * task.hierarchy_depth + marker + task.title); name.setData(Qt.ItemDataRole.UserRole,task.id); name.setToolTip(task_tooltip(task))
            owner = QTableWidgetItem(task.owner_name or "—"); owner.setData(Qt.ItemDataRole.UserRole,task.id)
            if task.id in self._parents:
                font=name.font(); font.setBold(True); name.setFont(font)
            self.task_table.setItem(index,0,name); self.task_table.setItem(index,1,owner); self.task_table.setRowHeight(index,ROW_HEIGHT)
        timeline_range = calculate_timeline_range(self.tasks, zoom=self.zoom,
            project_start=self.project.start_date if self.project else None,
            project_due=self.project.due_date if self.project else None)
        self.timeline.set_rows(display_rows,timeline_range,self.zoom)

    def _cell_clicked(self, row: int, column: int) -> None:
        task = self.visible_rows[row]
        if column == 0 and task.id in self._parents:
            self.toggle_collapsed(task.id)
        else:
            self.task_activated.emit(task.id)

    def _activate_left(self, row: int, _column: int) -> None:
        self.task_activated.emit(self.visible_rows[row].id)
