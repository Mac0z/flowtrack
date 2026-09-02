"""Pure, non-pixel coverage for the M7A Gantt foundation."""
import os
from dataclasses import replace
from datetime import date, timedelta
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame

from flowtrack.application.task_queries import TaskRow
from flowtrack.domain.enums import TaskPriority, TaskStatus
from flowtrack.ui.widgets.gantt_timeline import (
    GanttZoom, TimelineRange, calculate_timeline_range, date_to_x,
    day_header_labels, day_header_month_segments, pixels_per_day,
    task_bar_geometry, visible_hierarchy,
)


def row(title: str, *, depth: int = 0, parent=None, start=None, due=None, progress=0) -> TaskRow:
    return TaskRow(uuid4(), title, "", TaskStatus.NOT_STARTED, TaskPriority.MEDIUM,
        uuid4(), "Project", None, None, due, start, progress, 0, (), False, parent, depth)


def test_hierarchy_collapse_hides_all_descendants_and_expand_restores_order():
    parent=row("Parent"); child=row("Child",depth=1,parent=parent.id); grandchild=row("Grandchild",depth=2,parent=child.id); sibling=row("Sibling")
    tasks=[parent,child,grandchild,sibling]
    assert visible_hierarchy(tasks,{parent.id}) == [parent,sibling]
    assert visible_hierarchy(tasks,set()) == tasks


def test_range_bar_milestones_undated_and_progress_geometry():
    timeline=calculate_timeline_range((),today=date(2026,9,2))
    ranged=row("Range",start=date(2026,9,1),due=date(2026,9,5),progress=40)
    geometry=task_bar_geometry(ranged,timeline,GanttZoom.WEEK)
    assert geometry and not geometry.milestone and geometry.width == 5*pixels_per_day(GanttZoom.WEEK)
    assert geometry.progress_width == geometry.width*.4
    for task in (replace(ranged,due_date=ranged.start_date),replace(ranged,start_date=None),replace(ranged,due_date=None)):
        assert task_bar_geometry(task,timeline,GanttZoom.WEEK).milestone
    assert task_bar_geometry(replace(ranged,start_date=None,due_date=None),timeline,GanttZoom.WEEK) is None


def test_zoom_scales_coordinates_without_changing_task_data():
    task=row("Task",start=date(2026,9,1),due=date(2026,9,5)); original=task
    scales=[pixels_per_day(zoom) for zoom in GanttZoom]
    assert scales[0] > scales[1] > scales[2]
    for zoom in GanttZoom:
        task_bar_geometry(task,calculate_timeline_range([task],zoom=zoom),zoom)
    assert task == original


def test_timeline_range_padding_empty_fallback_and_today_coordinate():
    early=row("Early",start=date(2026,1,10)); late=row("Late",due=date(2026,3,20))
    timeline=calculate_timeline_range([early,late],zoom=GanttZoom.WEEK)
    assert timeline.start < early.start_date and timeline.end > late.due_date
    empty=calculate_timeline_range((),zoom=GanttZoom.WEEK,today=date(2026,9,2))
    assert empty.start < date(2026,9,2) < empty.end
    assert date_to_x(date(2026,9,2),empty,GanttZoom.WEEK) == (date(2026,9,2)-empty.start).days*pixels_per_day(GanttZoom.WEEK)


def test_day_header_segments_months_at_real_date_boundaries():
    timeline = TimelineRange(date(2026, 8, 31), date(2026, 10, 2))

    segments = day_header_month_segments(timeline)

    assert [(segment.start, segment.end, segment.label) for segment in segments] == [
        (date(2026, 8, 31), date(2026, 8, 31), "AUGUST 2026"),
        (date(2026, 9, 1), date(2026, 9, 30), "SEPTEMBER 2026"),
        (date(2026, 10, 1), date(2026, 10, 2), "OCTOBER 2026"),
    ]


def test_day_header_labels_and_geometry_follow_each_real_date():
    timeline = TimelineRange(date(2026, 8, 31), date(2026, 9, 6))
    expected = [("MON", "31"), ("TUE", "1"), ("WED", "2"), ("THU", "3"),
                ("FRI", "4"), ("SAT", "5"), ("SUN", "6")]

    for offset, labels in enumerate(expected):
        value = timeline.start + timedelta(days=offset)
        assert day_header_labels(value) == labels
        assert date_to_x(value, timeline, GanttZoom.DAY) == offset * pixels_per_day(GanttZoom.DAY)


def test_split_pane_uses_only_a_thin_divider_without_scrollbar_gutter(application):
    from flowtrack.ui.widgets.gantt_view import DAY_HEADER_HEIGHT, HEADER_HEIGHT, GanttView

    view = GanttView(queries=object())  # type: ignore[arg-type]

    assert view.splitter.handleWidth() == 2
    assert view.task_table.verticalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert view.task_table.frameShape() is QFrame.Shape.NoFrame
    view.set_zoom(GanttZoom.DAY)
    assert view.timeline.header_height == DAY_HEADER_HEIGHT
    assert view.task_table.horizontalHeader().height() == DAY_HEADER_HEIGHT
    view.set_zoom(GanttZoom.WEEK)
    assert view.timeline.header_height == HEADER_HEIGHT
    assert view.task_table.horizontalHeader().height() == HEADER_HEIGHT
