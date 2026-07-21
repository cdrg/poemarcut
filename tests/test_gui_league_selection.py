import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest
from PyQt6.QtWidgets import QApplication


class FakeThread:
    def __init__(self, *args: object, **kwargs: object) -> None:  # noqa: D107
        pass

    def start(self) -> None:
        pass


class BrokenDelayValidation:
    def __enter__(self) -> None:  # noqa: D105
        msg = "broken delay_validation"
        raise RuntimeError(msg)

    def __exit__(self, _exc_type: object, _exc_value: object, _traceback: object) -> bool:  # noqa: D105
        return False


def _import_gui_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, ModuleType]:
    monkeypatch.chdir(tmp_path)
    for module_name in ["poemarcut.settings", "poemarcut_gui"]:
        if module_name in sys.modules:
            del sys.modules[module_name]
    settings_mod = importlib.import_module("poemarcut.settings")
    gui_mod = importlib.import_module("poemarcut_gui")
    return settings_mod, gui_mod


def test_league_selection_updates_gui_settings_cache_after_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,  # noqa: ARG001
) -> None:
    _settings_mod, gui_mod = _import_gui_in_tmp(tmp_path, monkeypatch)
    monkeypatch.setattr(gui_mod.threading, "Thread", FakeThread)

    window = gui_mod.PoEMarcutGUI()

    assert window.league_combo.count() >= 2, "Expected at least two leagues in the combo"
    original_cache_league = window._settings_cache.currency.active_league
    original_active_league = window.settings_manager.settings.currency.active_league
    assert original_cache_league == original_active_league

    # Choose a different league than the initially active one.
    new_index = 1 if window.league_combo.currentIndex() == 0 else 0
    window._on_league_combo_changed(new_index)

    selected_text = window.league_combo.itemText(new_index)
    assert selected_text, "League combo item should have text"
    selected_league = window._league_display_to_id.get(selected_text)
    assert selected_league is not None, "Selected league should map back to a canonical id"
    assert selected_league != original_active_league

    assert window.settings_manager.settings.currency.active_league == selected_league
    assert window._settings_cache.currency.active_league == selected_league

    # Persist another setting through the cache and verify the active league remains selected.
    window.discount_percent_le.setText("20")
    window.process_qle_int("Logic", "discount_percent", window.discount_percent_le)
    window._flush_cached_settings()

    assert window.settings_manager.settings.currency.active_league == selected_league
    assert window._settings_cache.currency.active_league == selected_league


def test_max_actual_discount_change_refreshes_currency_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,  # noqa: ARG001
) -> None:
    _settings_mod, gui_mod = _import_gui_in_tmp(tmp_path, monkeypatch)
    monkeypatch.setattr(gui_mod.threading, "Thread", FakeThread)

    window = gui_mod.PoEMarcutGUI()
    refresh_calls: list[None] = []
    monkeypatch.setattr(window, "populate_currency_mappings", lambda: refresh_calls.append(None))

    window.max_actual_discount_le.setText("40")
    window.process_qle_int("Logic", "max_actual_discount", window.max_actual_discount_le)

    assert window.max_actual_discount_le.text() == "40"
    assert refresh_calls == [None]
