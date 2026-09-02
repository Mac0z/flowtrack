"""Qt-native interactive project Gantt with frozen task columns."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from uuid import UUID

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QButtonGroup, QFrame, QHeaderView,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from flowtrack.application.projects import ProjectQueryService, ProjectSummary
from flowtrack.application.task_execution import TaskExecutionService
from flowtrack.application.task_queries import TaskRow
from flowtrack.domain.enums import TaskStatus
from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.ui.theme import get_theme
from flowtrack.ui.theme.status import status_color
from flowtrack.ui.widgets.gantt_timeline import (
    ConnectorGeometry, DateChange, GanttZoom, TimelineRange, calculate_timeline_range, collapsed_descendant_dates,
    date_to_x, day_header_labels, day_header_month_segments, dependency_connectors, drag_days,
    move_task_dates, parent_ids, pixels_per_day, resize_task_due, resize_task_start,
    task_bar_geometry, visible_hierarchy,
)

ROW_HEIGHT = 38
HEADER_HEIGHT = 42
DAY_HEADER_HEIGHT = 66
MILESTONE_SIZE = 7
DRAG_THRESHOLD = 4
EDGE_HIT_WIDTH = 6


def paint_dependency_connector(
    painter: QPainter, connector: ConnectorGeometry, connector_colour: QColor,
) -> None:
    """Stroke one routed connector and fill only its successor arrowhead."""
    painter.save()
    connector_pen = QPen(connector_colour, 1.5)
    painter.setPen(connector_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    first = connector.points[0]
    path.moveTo(*first)
    for point in connector.points[1:]:
        path.lineTo(*point)
    painter.drawPath(path)

    end_x, end_y = connector.points[-1]
    painter.setBrush(connector_colour)
    painter.drawPolygon(QPolygonF([
        QPointF(end_x, end_y),
        QPointF(end_x - 6, end_y - 4),
        QPointF(end_x - 6, end_y + 4),
    ]))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.restore()


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
    date_change_requested = Signal(object, object, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.theme = get_theme(ApplicationSettings().theme_id)
        self.rows: list[TaskRow] = []
        self.zoom = GanttZoom.WEEK
        self.timeline_range = calculate_timeline_range((), zoom=self.zoom)
        self.has_dated_work = False
        self.editable_ids: set[UUID] = set()
        self._press_task: TaskRow | None = None
        self._press_x = 0.0
        self._interaction = ""
        self._dragging = False
        self._preview: DateChange | None = None
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.horizontalScrollBar().valueChanged.connect(self.viewport().update)
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)

    @property
    def header_height(self) -> int:
        return DAY_HEADER_HEIGHT if self.zoom is GanttZoom.DAY else HEADER_HEIGHT

    def set_rows(self, rows: list[TaskRow], timeline_range: TimelineRange, zoom: GanttZoom,
                 *, editable_ids: set[UUID] | None = None) -> None:
        self.rows, self.timeline_range, self.zoom = list(rows), timeline_range, zoom
        self.has_dated_work = any(row.start_date or row.due_date for row in rows)
        self.editable_ids = set(editable_ids if editable_ids is not None else (row.id for row in rows))
        content_width = max(1, int(timeline_range.days * pixels_per_day(zoom)))
        self.horizontalScrollBar().setRange(0, max(0, content_width - self.viewport().width()))
        content_height = len(rows) * ROW_HEIGHT
        self.verticalScrollBar().setRange(0, max(0, content_height - (self.viewport().height() - self.header_height)))
        self.verticalScrollBar().setPageStep(max(ROW_HEIGHT, self.viewport().height() - self.header_height))
        self.viewport().update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.set_rows(self.rows, self.timeline_range, self.zoom, editable_ids=self.editable_ids)

    def _bar_hit(self, task: TaskRow, viewport_x: float) -> str:
        if task.id not in self.editable_ids:
            return ""
        geometry = task_bar_geometry(task, self.timeline_range, self.zoom)
        if geometry is None:
            return ""
        content_x = viewport_x + self.horizontalScrollBar().value()
        if geometry.milestone:
            return "move" if abs(content_x - geometry.x) <= MILESTONE_SIZE + 3 else ""
        if not geometry.x - 1 <= content_x <= geometry.x + geometry.width + 1:
            return ""
        if content_x <= geometry.x + EDGE_HIT_WIDTH:
            return "resize_start"
        if content_x >= geometry.x + geometry.width - EDGE_HIT_WIDTH:
            return "resize_due"
        return "move"

    def _row_at(self, position: QPoint) -> TaskRow | None:
        if position.y() < self.header_height:
            return None
        index = (position.y() - self.header_height + self.verticalScrollBar().value()) // ROW_HEIGHT
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        task = self._row_at(event.position().toPoint())
        if self._press_task and event.buttons() & Qt.MouseButton.LeftButton and self._interaction:
            delta_pixels = event.position().x() - self._press_x
            if abs(delta_pixels) >= DRAG_THRESHOLD:
                self._dragging = True
                days = drag_days(delta_pixels, self.zoom)
                if self._interaction == "move":
                    self._preview = move_task_dates(self._press_task.start_date, self._press_task.due_date, days)
                elif self._interaction == "resize_start":
                    self._preview = resize_task_start(self._press_task.start_date, self._press_task.due_date, days)
                else:
                    self._preview = resize_task_due(self._press_task.start_date, self._press_task.due_date, days)
                if self._preview:
                    self.viewport().setToolTip(self._preview_text(self._preview))
                self.viewport().update()
            return
        interaction = self._bar_hit(task, event.position().x()) if task else ""
        self.viewport().setCursor(Qt.CursorShape.SizeHorCursor if interaction.startswith("resize") else
                                  Qt.CursorShape.OpenHandCursor if interaction == "move" else Qt.CursorShape.ArrowCursor)
        self.viewport().setToolTip(task_tooltip(task) if task and (task.start_date or task.due_date) else "")
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        task = self._row_at(event.position().toPoint())
        if task and event.button() == Qt.MouseButton.LeftButton:
            self._interaction = self._bar_hit(task, event.position().x())
            self._press_task = task
            self._press_x = event.position().x()
            self._dragging = False
            self._preview = None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        task, change, interaction = self._press_task, self._preview, self._interaction
        dragged = self._dragging
        self._press_task = None; self._preview = None; self._interaction = ""; self._dragging = False
        self.viewport().update()
        if event.button() == Qt.MouseButton.LeftButton and task:
            if dragged and change and (change.start_date, change.due_date) != (task.start_date, task.due_date):
                self.date_change_requested.emit(task, change, interaction)
            elif not dragged:
                self.task_activated.emit(task.id)
        super().mouseReleaseEvent(event)

    @staticmethod
    def _preview_text(change: DateChange) -> str:
        if change.start_date and change.due_date:
            return f"{change.start_date:%d %b} – {change.due_date:%d %b}"
        value = change.start_date or change.due_date
        return value.strftime("%d %b %Y") if value else ""

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
        header_height = self.header_height
        painter.save(); painter.setClipRect(0, header_height, width, height - header_height)
        # Alternating rows and deterministic date separators.
        for index, task in enumerate(self.rows):
            y = header_height + index * ROW_HEIGHT - vertical
            if y + ROW_HEIGHT < header_height or y > height: continue
            if index % 2: painter.fillRect(0, y, width, ROW_HEIGHT, QColor(colors.surface_secondary))
            painter.setPen(QPen(QColor(colors.divider), 1)); painter.drawLine(0, y + ROW_HEIGHT - 1, width, y + ROW_HEIGHT - 1)
            painted_task = task
            if self._press_task and task.id == self._press_task.id and self._preview:
                painted_task = replace(task, start_date=self._preview.start_date, due_date=self._preview.due_date)
            geometry = task_bar_geometry(painted_task, self.timeline_range, self.zoom)
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
                if task.id in self.editable_ids and (self._press_task and task.id == self._press_task.id):
                    painter.setPen(QPen(bar_color.lighter(150), 2))
                    painter.drawLine(int(x + 2), int(centre_y - 6), int(x + 2), int(centre_y + 6))
                    painter.drawLine(int(x + geometry.width - 2), int(centre_y - 6), int(x + geometry.width - 2), int(centre_y + 6))
        # Dependencies are painted as one lightweight overlay and only for visible rows.
        connector_colour = QColor(colors.text_muted)
        for connector in dependency_connectors(self.rows, self.timeline_range, self.zoom,
                row_height=ROW_HEIGHT, header_height=header_height,
                horizontal_scroll=horizontal, vertical_scroll=vertical):
            paint_dependency_connector(painter, connector, connector_colour)
        # Calendar grid and today marker are deliberately drawn over row backgrounds.
        step = {GanttZoom.DAY: 1, GanttZoom.WEEK: 7, GanttZoom.MONTH: 1}[self.zoom]
        cursor = self.timeline_range.start
        while cursor <= self.timeline_range.end:
            boundary = (self.zoom is GanttZoom.DAY or
                        self.zoom is GanttZoom.WEEK and cursor.weekday() == 0 or
                        self.zoom is GanttZoom.MONTH and cursor.day == 1)
            if boundary:
                x = date_to_x(cursor, self.timeline_range, self.zoom) - horizontal
                painter.setPen(QPen(QColor(colors.divider), 1)); painter.drawLine(int(x), header_height, int(x), height)
            cursor += timedelta(days=step)
        today_x = date_to_x(date.today(), self.timeline_range, self.zoom) - horizontal
        painter.setPen(QPen(QColor(colors.accent_hover), 2)); painter.drawLine(int(today_x), header_height, int(today_x), height)
        painter.restore()
        # Fixed header is painted last so neither scrollbar moves it vertically.
        painter.fillRect(0, 0, width, header_height, QColor(colors.surface_elevated))
        painter.setPen(QPen(QColor(colors.border_subtle), 1)); painter.drawLine(0, header_height-1, width, header_height-1)
        self._paint_header(painter, horizontal, width)
        if not self.has_dated_work:
            painter.setPen(QColor(colors.text_muted)); painter.drawText(QRectF(20, header_height+18, width-40, 50), Qt.AlignmentFlag.AlignHCenter, "Add start or due dates to see task bars on the timeline.")

    def _paint_header(self, painter: QPainter, horizontal: int, width: int) -> None:
        if self.zoom is GanttZoom.DAY:
            self._paint_day_header(painter, horizontal)
            return
        colors = self.theme.colors; cursor = self.timeline_range.start
        painter.setPen(QColor(colors.text_secondary))
        while cursor <= self.timeline_range.end:
            show = self.zoom is GanttZoom.WEEK and cursor.weekday() == 0 or self.zoom is GanttZoom.MONTH and cursor.day == 1
            if show:
                x = date_to_x(cursor, self.timeline_range, self.zoom) - horizontal
                label = f"Week of {cursor.strftime('%d %b')}" if self.zoom is GanttZoom.WEEK else cursor.strftime("%B %Y")
                painter.drawText(QRectF(x+6, 0, max(80, width), HEADER_HEIGHT), Qt.AlignmentFlag.AlignVCenter, label)
            cursor += timedelta(days=1)

    def _paint_day_header(self, painter: QPainter, horizontal: int) -> None:
        colors = self.theme.colors
        day_width = pixels_per_day(GanttZoom.DAY)
        month_height = 25
        today = date.today()
        cursor = self.timeline_range.start
        while cursor <= self.timeline_range.end:
            x = date_to_x(cursor, self.timeline_range, GanttZoom.DAY) - horizontal
            cell = QRectF(x, month_height, day_width, DAY_HEADER_HEIGHT - month_height)
            if cursor.weekday() >= 5:
                painter.fillRect(cell, QColor(colors.surface_secondary))
            if cursor == today:
                accent = QColor(colors.accent); accent.setAlpha(40)
                painter.fillRect(cell, accent)
            painter.setPen(QPen(QColor(colors.divider), 1))
            painter.drawLine(int(x), month_height, int(x), DAY_HEADER_HEIGHT)
            weekday, day_number = day_header_labels(cursor)
            secondary_font = QFont(painter.font()); secondary_font.setPixelSize(self.theme.typography.small)
            painter.setFont(secondary_font); painter.setPen(QColor(colors.text_muted))
            painter.drawText(QRectF(x, month_height + 2, day_width, 17), Qt.AlignmentFlag.AlignCenter, weekday)
            primary_font = QFont(painter.font()); primary_font.setPixelSize(self.theme.typography.body); primary_font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(primary_font); painter.setPen(QColor(colors.accent if cursor == today else colors.text_primary))
            painter.drawText(QRectF(x, month_height + 18, day_width, 20), Qt.AlignmentFlag.AlignCenter, day_number)
            cursor += timedelta(days=1)
        month_font = QFont(painter.font()); month_font.setPixelSize(self.theme.typography.small); month_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(month_font); painter.setPen(QColor(colors.text_secondary))
        for segment in day_header_month_segments(self.timeline_range):
            x = date_to_x(segment.start, self.timeline_range, GanttZoom.DAY) - horizontal
            segment_width = ((segment.end - segment.start).days + 1) * day_width
            painter.drawText(QRectF(x, 0, segment_width, month_height), Qt.AlignmentFlag.AlignCenter, segment.label)
        painter.setPen(QPen(QColor(colors.border_subtle), 1))
        painter.drawLine(0, month_height, self.viewport().width(), month_height)


class GanttView(QWidget):
    """Project-aware split view; task data remains immutable and query-backed."""
    task_activated = Signal(object)
    data_changed = Signal()

    def __init__(self, queries: ProjectQueryService, task_service: TaskExecutionService | None = None, parent=None) -> None:
        super().__init__(parent); self.queries = queries; self.task_service = task_service; self.project_id: UUID | None = None
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
        self.splitter.setHandleWidth(2)
        self.splitter.setStyleSheet(f"QSplitter::handle {{ background: {theme.colors.divider}; }}")
        self.task_table = QTableWidget(0,2); self.task_table.setHorizontalHeaderLabels(["Task","Owner"]); self.task_table.verticalHeader().hide()
        self.task_table.horizontalHeader().setFixedHeight(HEADER_HEIGHT); self.task_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch); self.task_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Fixed); self.task_table.setColumnWidth(1,120)
        self.task_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.task_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); self.task_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel); self.task_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); self.task_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); self.task_table.setFrameShape(QFrame.Shape.NoFrame); self.task_table.setMinimumWidth(300)
        self.task_table.cellClicked.connect(self._cell_clicked); self.task_table.cellDoubleClicked.connect(self._activate_left)
        self.timeline = GanttTimeline(); self.timeline.task_activated.connect(self.task_activated)
        self.timeline.date_change_requested.connect(self.request_date_change)
        self.splitter.addWidget(self.task_table); self.splitter.addWidget(self.timeline); self.splitter.setSizes([390,700]); self.splitter.setStretchFactor(1,1); root.addWidget(self.splitter,1)
        left_scroll, right_scroll = self.task_table.verticalScrollBar(), self.timeline.verticalScrollBar()
        left_scroll.valueChanged.connect(right_scroll.setValue); right_scroll.valueChanged.connect(left_scroll.setValue)

    def set_project(self, project_id: UUID | None, project: ProjectSummary | None = None) -> None:
        self.project_id, self.project = project_id, project; self.collapsed.clear(); self.refresh()

    def refresh(self) -> None:
        self.tasks = self.queries.project_tasks(self.project_id) if self.project_id else []
        self._parents = parent_ids(self.tasks); self._rebuild()

    def set_zoom(self, zoom: GanttZoom | str) -> None:
        self.zoom = GanttZoom(zoom); self.zoom_buttons[self.zoom].setChecked(True)
        self.task_table.horizontalHeader().setFixedHeight(DAY_HEADER_HEIGHT if self.zoom is GanttZoom.DAY else HEADER_HEIGHT)
        self._rebuild()

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
        # Calculated collapsed spans are display-only; explicit parent dates remain editable.
        editable_ids = {task.id for task in self.visible_rows if task.start_date or task.due_date}
        self.timeline.set_rows(display_rows,timeline_range,self.zoom,editable_ids=editable_ids)

    def confirm_date_change(self, task: TaskRow, change: DateChange, interaction: str) -> bool:
        action = "Move" if interaction == "move" else "Change start date for" if interaction == "resize_start" else "Change due date for"
        lines = [f"{action} '{task.title}'?"]
        if task.start_date != change.start_date:
            lines.append(f"Start: {self._format_date(task.start_date)} → {self._format_date(change.start_date)}")
        if task.due_date != change.due_date:
            lines.append(f"Due: {self._format_date(task.due_date)} → {self._format_date(change.due_date)}")
        dialog = QMessageBox(QMessageBox.Icon.Question, "Confirm task dates", "\n".join(lines), parent=self)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(QMessageBox.StandardButton.Ok); dialog.setEscapeButton(QMessageBox.StandardButton.Cancel)
        return QMessageBox.StandardButton(dialog.exec()) == QMessageBox.StandardButton.Ok

    @staticmethod
    def _format_date(value: date | None) -> str:
        return value.strftime("%d %b") if value else "—"

    def request_date_change(self, task: TaskRow, change: DateChange, interaction: str) -> bool:
        if self.task_service is None or not self.confirm_date_change(task, change, interaction):
            self._rebuild(); return False
        try:
            self.task_service.update_task(task.id, start_date=change.start_date, due_date=change.due_date)
        except Exception as exc:
            QMessageBox.warning(self, "Could not change task dates", f"The task dates were not changed.\n\n{exc}")
            self.refresh(); return False
        self.refresh(); self.data_changed.emit(); return True

    def _cell_clicked(self, row: int, column: int) -> None:
        task = self.visible_rows[row]
        if column == 0 and task.id in self._parents:
            self.toggle_collapsed(task.id)
        else:
            self.task_activated.emit(task.id)

    def _activate_left(self, row: int, _column: int) -> None:
        self.task_activated.emit(self.visible_rows[row].id)
