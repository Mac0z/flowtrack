import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from flowtrack.app import create_application
from flowtrack.ui.windows.main_window import MainWindow


def test_application_shell_can_be_created() -> None:
    application = create_application(["flowtrack-test"])
    window = MainWindow()

    assert application.applicationName() == "FlowTrack"
    assert window.windowTitle() == "FlowTrack"
    assert window.centralWidget() is not None

    window.close()
    application.quit()

