import importlib
import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QMoveEvent


def _import_gui_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    monkeypatch.chdir(tmp_path)
    for module_name in ["poemarcut.settings", "poemarcut_gui"]:
        if module_name in sys.modules:
            del sys.modules[module_name]
    settings_mod = importlib.import_module("poemarcut.settings")
    gui_mod = importlib.import_module("poemarcut_gui")
    return settings_mod, gui_mod


class FakeThread:
    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize a fake thread for testing."""

    def start(self) -> None:
        pass


def test_move_event_persists_client_geometry_coordinates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_mod, gui_mod = _import_gui_in_tmp(tmp_path, monkeypatch)
    monkeypatch.setattr(gui_mod.threading, "Thread", FakeThread)

    window = gui_mod.PoEMarcutGUI()
    window._settings_cache = window.settings_manager.settings

    expected_geometry = QRect(100, 150, 450, 400)
    frame_geometry = QRect(100, 170, 470, 440)

    monkeypatch.setattr(gui_mod.PoEMarcutGUI, "geometry", lambda _: expected_geometry)
    monkeypatch.setattr(gui_mod.PoEMarcutGUI, "frameGeometry", lambda _: frame_geometry)

    event = QMoveEvent(QPoint(expected_geometry.x(), expected_geometry.y()), QPoint(0, 0))
    window.moveEvent(event)
    window._flush_cached_settings()

    assert window.settings_manager.settings.gui.position.x == expected_geometry.x()
    assert window.settings_manager.settings.gui.position.y == expected_geometry.y()
