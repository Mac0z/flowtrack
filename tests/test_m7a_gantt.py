"""Pure, non-pixel coverage for the M7A Gantt foundation."""
from dataclasses import replace
from datetime import date
from uuid import uuid4

from flowtrack.application.task_queries import TaskRow
from flowtrack.domain.enums import TaskPriority, TaskStatus
from flowtrack.ui.widgets.gantt_timeline import (
    GanttZoom, calculate_timeline_range, date_to_x, pixels_per_day,
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
