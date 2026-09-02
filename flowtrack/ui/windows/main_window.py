"""FlowTrack shell with M4 task execution surfaces."""

from PySide6.QtCore import QEvent
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QSizePolicy, QStackedWidget,
    QStyle, QVBoxLayout, QWidget, QMessageBox,
)
from sqlalchemy import create_engine
from flowtrack.persistence.models import Base
from flowtrack.persistence.database import session_factory
from flowtrack.application.task_execution import TaskExecutionService, TaskValidationError
from flowtrack.application.task_queries import TaskQueryService
from flowtrack.application.projects import ProjectQueryService, ProjectService

from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.ui.dialogs.command_palette import CommandPalette
from flowtrack.ui.navigation import Destination, NavigationController, PRIMARY_NAVIGATION
from flowtrack.ui.shortcuts import shell_shortcuts
from flowtrack.ui.views.placeholder import PlaceholderView
from flowtrack.ui.views.dashboard import DashboardView
from flowtrack.ui.views.my_tasks import MyTasksView
from flowtrack.ui.views.projects import ProjectsView
from flowtrack.ui.views.calendar import CalendarView
from flowtrack.ui.dialogs.quick_capture import QuickCaptureDialog
from flowtrack.ui.dialogs.people_tags import PeopleTagsDialog
from flowtrack.ui.widgets.task_inspector import TaskInspector
from flowtrack.ui.widgets import CommandField, NavigationButton


class MainWindow(QMainWindow):
    """Persistent sidebar and independently controlled central page stack."""

    def __init__(self, settings: ApplicationSettings | None = None,
                 task_service: TaskExecutionService | None = None,
                 task_queries: TaskQueryService | None = None) -> None:
        super().__init__()
        self.settings = settings or ApplicationSettings()
        self.setWindowTitle("FlowTrack")
        self.setMinimumSize(960, 640)
        self.resize(1280, 800)
        if task_service is None or task_queries is None:
            engine = create_engine("sqlite+pysqlite:///:memory:")
            Base.metadata.create_all(engine); factory = session_factory(engine)
            task_service, task_queries = TaskExecutionService(factory), TaskQueryService(factory)
        self.task_service, self.task_queries = task_service, task_queries
        self.project_service = ProjectService(task_service._factory)
        self.project_queries = ProjectQueryService(task_service._factory)
        self.command_palette = CommandPalette(self)
        self.command_palette.command_triggered.connect(self._execute_command)
        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("contentArea")
        self.pages: dict[Destination, QWidget] = {}
        self.navigation_buttons: dict[Destination, NavigationButton] = {}
        try:
            initial = Destination(self.settings.last_destination)
        except ValueError:
            initial = Destination.DASHBOARD
        self.navigation = NavigationController(initial)
        self.inspector = TaskInspector(self.task_service, self.task_queries)
        self.inspector.deleted.connect(self._delete_inspected_task)
        self.quick_capture = QuickCaptureDialog(self.task_service, self.task_queries, self)
        # The dialog is shared by every capture entry point, so its successful
        # creation signal has one application-wide refresh path.
        self.quick_capture.task_created.connect(self._task_created)
        self.people_tags = PeopleTagsDialog(self.task_service, self.task_queries, self)
        self._build_shell()
        self._build_actions()
        self.navigation.destination_changed.connect(self._show_destination)
        self._show_destination(initial)
        geometry = self.settings.window_geometry()
        state = self.settings.window_state()
        if not geometry.isEmpty():
            self.restoreGeometry(geometry)
        if not state.isEmpty():
            self.restoreState(state)

    @property
    def active_destination(self) -> Destination:
        return self.navigation.destination

    def navigate(self, destination: Destination) -> None:
        self.navigation.navigate(destination)
        # Ensure initial/same-destination programmatic navigation remains idempotent.
        self._show_destination(destination)

    def open_command_palette(self) -> None:
        self.command_palette.open()

    def _build_shell(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._create_sidebar())
        for item in PRIMARY_NAVIGATION:
            if item.destination is Destination.DASHBOARD:
                page = DashboardView(self.task_queries)
                page.quick_add_requested.connect(self.open_quick_task); page.global_search_requested.connect(self.open_command_palette); page.task_selected.connect(self.open_inspector)
            elif item.destination is Destination.MY_TASKS:
                page = MyTasksView(self.task_service, self.task_queries, self.settings)
                page.task_selected.connect(self.open_inspector); page.data_changed.connect(self.refresh_execution_views)
            elif item.destination is Destination.PROJECTS:
                page = ProjectsView(self.project_service, self.project_queries, self.task_service)
                page.task_selected.connect(self.open_inspector)
                page.new_task_requested.connect(self.open_project_task)
                page.project_changed.connect(self.refresh_project_views)
            elif item.destination is Destination.CALENDAR:
                page = CalendarView(self.task_service, self.task_queries)
                page.task_selected.connect(self.open_inspector)
                page.data_changed.connect(self.refresh_project_views)
            else:
                page = PlaceholderView(item.label)
            self.pages[item.destination] = page
            self.page_stack.addWidget(page)
        root_layout.addWidget(self.page_stack, 1)
        root_layout.addWidget(self.inspector)
        self.setCentralWidget(root)

    def _create_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(232)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 24, 16, 18)
        layout.setSpacing(5)
        brand = QLabel("FlowTrack")
        brand.setObjectName("brand")
        layout.addWidget(brand)
        search = CommandField()
        search.setPlaceholderText("Search or command")
        search.setReadOnly(True)
        search.setAccessibleName("Open command palette")
        search.setToolTip("Open command palette")
        search.installEventFilter(self)
        self.command_entry = search
        layout.addSpacing(15)
        layout.addWidget(search)
        layout.addSpacing(13)
        group = QButtonGroup(self)
        group.setExclusive(True)
        icons = (QStyle.StandardPixmap.SP_ComputerIcon, QStyle.StandardPixmap.SP_FileDialogListView,
                 QStyle.StandardPixmap.SP_DirIcon, QStyle.StandardPixmap.SP_FileDialogDetailedView,
                 QStyle.StandardPixmap.SP_ArrowForward, QStyle.StandardPixmap.SP_FileDialogInfoView,
                 QStyle.StandardPixmap.SP_FileDialogContentsView)
        for item, icon in zip(PRIMARY_NAVIGATION, icons, strict=True):
            button = NavigationButton(item.label)
            button.setIcon(self.style().standardIcon(icon))
            button.clicked.connect(lambda _checked=False, destination=item.destination: self.navigate(destination))
            group.addButton(button)
            self.navigation_buttons[item.destination] = button
            layout.addWidget(button)
        layout.addSpacing(16)
        divider = QLabel("PINNED PROJECTS")
        divider.setObjectName("mutedText")
        layout.addWidget(divider)
        self.pinned_projects_widget = QWidget(); self.pinned_projects_layout = QVBoxLayout(self.pinned_projects_widget); self.pinned_projects_layout.setContentsMargins(0,0,0,0); self.pinned_projects_layout.setSpacing(2); layout.addWidget(self.pinned_projects_widget)
        manage = NavigationButton("Owners & Tags")
        manage.setCheckable(False); manage.clicked.connect(self.people_tags.open)
        layout.addWidget(manage)
        layout.addStretch()
        sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.refresh_pinned_projects()
        return sidebar

    def _build_actions(self) -> None:
        shortcuts = shell_shortcuts()
        self.command_action = QAction("Command Palette", self)
        self.command_action.setShortcut(shortcuts.command_palette)
        self.command_action.setShortcutContext(self.command_action.shortcutContext())
        self.command_action.triggered.connect(self.open_command_palette)
        self.addAction(self.command_action)
        self.quick_task_action = QAction("Quick Task", self)
        self.quick_task_action.setShortcut(shortcuts.quick_task)
        self.quick_task_action.triggered.connect(self.open_quick_task)
        self.addAction(self.quick_task_action)
        self.active_search_action = QAction("Search Active View", self)
        self.active_search_action.setShortcut(shortcuts.active_view_search)
        self.active_search_action.triggered.connect(self.focus_active_search)
        self.addAction(self.active_search_action)

    def _show_destination(self, destination: Destination) -> None:
        self.page_stack.setCurrentWidget(self.pages[destination])
        self.navigation_buttons[destination].setChecked(True)
        self.settings.last_destination = destination.value

    def open_quick_task(self) -> None:
        self.quick_capture.open()

    def _task_created(self, task_id: object) -> None:
        self.refresh_project_views()

    def open_project_task(self, project_id: object) -> None:
        self.quick_capture.open_for_project(project_id)

    def open_project(self, project_id: object) -> None:
        self.navigate(Destination.PROJECTS)
        page = self.pages[Destination.PROJECTS]
        if isinstance(page, ProjectsView): page.open_project(project_id)

    def refresh_pinned_projects(self) -> None:
        if not hasattr(self, "pinned_projects_layout"): return
        while self.pinned_projects_layout.count():
            item=self.pinned_projects_layout.takeAt(0); widget=item.widget()
            if widget: widget.deleteLater()
        projects=self.project_queries.pinned_projects()
        if not projects:
            hint=QLabel("No pinned projects"); hint.setObjectName("mutedText"); self.pinned_projects_layout.addWidget(hint)
        for project in projects[:8]:
            button=NavigationButton(project.name); button.setCheckable(False); button.setToolTip(project.name); button.clicked.connect(lambda _=False,pid=project.id:self.open_project(pid)); self.pinned_projects_layout.addWidget(button)

    def refresh_project_views(self) -> None:
        page=self.pages.get(Destination.PROJECTS)
        if isinstance(page,ProjectsView): page.refresh()
        self.refresh_pinned_projects(); self.refresh_execution_views()

    def refresh_execution_views(self) -> None:
        dashboard = self.pages.get(Destination.DASHBOARD); tasks = self.pages.get(Destination.MY_TASKS)
        if isinstance(dashboard, DashboardView): dashboard.refresh()
        if isinstance(tasks, MyTasksView): tasks.refresh()
        calendar = self.pages.get(Destination.CALENDAR)
        if isinstance(calendar, CalendarView): calendar.refresh()
        if self.inspector.isVisible() and self.inspector.task_id is not None:
            self.inspector.load_task(self.inspector.task_id)

    def open_inspector(self, task_id: object) -> None:
        self.inspector.load_task(task_id)
        try: self.inspector.saved.disconnect(self.refresh_execution_views)
        except RuntimeError: pass
        self.inspector.saved.connect(self.refresh_project_views)

    def focus_active_search(self) -> None:
        page = self.pages.get(self.active_destination)
        if isinstance(page, MyTasksView): page.focus_search()

    def _execute_command(self, command: str) -> None:
        actions = {"Quick Task": self.open_quick_task,
                   "Go to Dashboard": lambda: self.navigate(Destination.DASHBOARD),
                   "Go to My Tasks": lambda: self.navigate(Destination.MY_TASKS),
                   "Go to Projects": lambda: self.navigate(Destination.PROJECTS),
                   "Open Settings": lambda: self.navigate(Destination.SETTINGS)}
        action = actions.get(command)
        if action: action()

    def _delete_inspected_task(self) -> None:
        task_id = self.inspector.task_id
        if task_id is None: return
        answer = QMessageBox.question(self, "Delete task?", "Delete this task? Child tasks and dependencies may also be removed.",
                                      QMessageBox.StandardButton.Delete | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Delete: return
        try: self.task_service.delete_task(task_id)
        except TaskValidationError:
            confirm = QMessageBox.question(self, "Delete task and children?", "This task has children. Delete the entire task hierarchy?",
                                           QMessageBox.StandardButton.Delete | QMessageBox.StandardButton.Cancel,
                                           QMessageBox.StandardButton.Cancel)
            if confirm != QMessageBox.StandardButton.Delete: return
            self.task_service.delete_task(task_id, allow_with_children=True)
        self.inspector.close_inspector(); self.refresh_project_views()

    def keyPressEvent(self, event) -> None:
        if event.key() == 0x01000000 and self.inspector.isVisible(): self.inspector.close_inspector(); return
        super().keyPressEvent(event)

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self.command_entry and event.type() == QEvent.Type.MouseButtonPress:
            self.open_command_palette()
            return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.settings.save_window(self.saveGeometry(), self.saveState())
        super().closeEvent(event)
