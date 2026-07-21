import importlib
import logging
import sys
from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch
from PyQt6.QtWidgets import QApplication

from poemarcut import currency

tmp_yaml = "tmpstandard-1.yaml"


def test_empty_market_response_detected(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: MonkeyPatch
) -> None:
    cache_file = tmp_path / tmp_yaml
    cache_file.write_text(
        "core:\n  items: []\n  primary: chaos\n  rates: {}\n  secondary: divine\nitems: []\nlines: []\n",
        encoding="utf-8",
    )

    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)
    result = currency._retrieve_currency_prices(game=1, league="tmpstandard", update=False)

    assert result.get("lines") == []
    assert result.get("core", {}).get("primary") == "chaos"
    assert "Empty market response" in caplog.text


def test_gui_shows_warning_for_empty_market_response(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    qapp: QApplication,  # noqa: ARG001
) -> None:
    empty_data = {
        "core": {"primary": "chaos", "items": [], "rates": {}, "secondary": "divine"},
        "lines": [],
    }

    class FakeStore:
        def get_data(self, game: int, league: str, *, update: bool) -> dict:  # noqa: ARG002
            return empty_data

    monkeypatch.chdir(tmp_path)
    for module_name in ["poemarcut.settings", "poemarcut_gui"]:
        if module_name in sys.modules:
            del sys.modules[module_name]

    settings = importlib.import_module("poemarcut.settings")
    gui_mod = importlib.import_module("poemarcut_gui")

    window = gui_mod.PoEMarcutGUI()
    window.settings_manager = settings.settings_manager
    monkeypatch.setattr(currency, "store", FakeStore())

    window.populate_currency_mappings()

    assert window.currency_list.count() == 1
    item = window.currency_list.item(0)
    assert item is not None
    assert item.text() == "No currency data was returned for league tmpstandard."
