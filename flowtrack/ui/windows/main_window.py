"""FlowTrack M3 application shell."""

from PySide6.QtCore import QEvent
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QSizePolicy, QStackedWidget,
    QStyle, QVBoxLayout, QWidget,
)

from flowtrack.infrastructure.settings import ApplicationSettings
from flowtrack.ui.dialogs.command_palette import CommandPalette
from flowtrack.ui.navigation import Destination, NavigationController, PRIMARY_NAVIGATION
from flowtrack.ui.shortcuts import shell_shortcuts
from flowtrack.ui.views.placeholder import PlaceholderView
from flowtrack.ui.widgets import CommandField, NavigationButton


class MainWindow(QMainWindow):
    """Persistent sidebar and independently controlled central page stack."""

    def __init__(self, settings: ApplicationSettings | None = None) -> None:
        super().__init__()
        self.settings = settings or ApplicationSettings()
        self.setWindowTitle("FlowTrack")
        self.setMinimumSize(960, 640)
        self.resize(1280, 800)
        self.command_palette = CommandPalette(self)
        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("contentArea")
        self.pages: dict[Destination, PlaceholderView] = {}
        self.navigation_buttons: dict[Destination, NavigationButton] = {}
        try:
            initial = Destination(self.settings.last_destination)
        except ValueError:
            initial = Destination.DASHBOARD
        self.navigation = NavigationController(initial)
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
            page = PlaceholderView(item.label)
            self.pages[item.destination] = page
            self.page_stack.addWidget(page)
        root_layout.addWidget(self.page_stack, 1)
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
        pinned_hint = QLabel("Project shortcuts will appear here")
        pinned_hint.setObjectName("mutedText")
        pinned_hint.setWordWrap(True)
        layout.addWidget(pinned_hint)
        layout.addStretch()
        sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        return sidebar

    def _build_actions(self) -> None:
        shortcuts = shell_shortcuts()
        self.command_action = QAction("Command Palette", self)
        self.command_action.setShortcut(shortcuts.command_palette)
        self.command_action.setShortcutContext(self.command_action.shortcutContext())
        self.command_action.triggered.connect(self.open_command_palette)
        self.addAction(self.command_action)
        self.quick_task_action = QAction("Quick Task (coming in M4)", self)
        self.quick_task_action.setShortcut(shortcuts.quick_task)
        self.quick_task_action.setEnabled(False)
        self.addAction(self.quick_task_action)
        self.active_search_action = QAction("Search Active View (not available)", self)
        self.active_search_action.setShortcut(shortcuts.active_view_search)
        self.active_search_action.setEnabled(False)
        self.addAction(self.active_search_action)

    def _show_destination(self, destination: Destination) -> None:
        self.page_stack.setCurrentWidget(self.pages[destination])
        self.navigation_buttons[destination].setChecked(True)
        self.settings.last_destination = destination.value

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self.command_entry and event.type() == QEvent.Type.MouseButtonPress:
            self.open_command_palette()
            return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.settings.save_window(self.saveGeometry(), self.saveState())
        super().closeEvent(event)
