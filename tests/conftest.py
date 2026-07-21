"""Shared pytest fixtures for PoEMarcut tests."""

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Provide a single `QApplication` instance for tests that construct Qt widgets.

    PyQt6 aborts the process if a widget is constructed before a `QApplication`
    exists, so any test that instantiates `PoEMarcutGUI` or other widgets must
    depend on this fixture.

    Returns:
        QApplication: The shared application instance for the test session.

    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
