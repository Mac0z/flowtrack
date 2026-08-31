"""Shared pytest fixtures."""

import pytest


@pytest.fixture(scope="session")
def application():
    """Return the process-wide QApplication, creating it only when necessary."""
    from PySide6.QtWidgets import QApplication

    from flowtrack.app import create_application

    existing = QApplication.instance()
    app = existing if existing is not None else create_application(["flowtrack-test"])
    yield app

