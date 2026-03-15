import importlib
import logging
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _import_settings_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.chdir(tmp_path)
    # Ensure a fresh import so module-level SettingsManager runs in tmp cwd
    if "poemarcut.settings" in sys.modules:
        del sys.modules["poemarcut.settings"]
    return importlib.import_module("poemarcut.settings")


def test_missing_settings_creates_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings_mod = _import_settings_in_tmp(tmp_path, monkeypatch)
    # settings.yaml should be created by the manager when missing
    assert (tmp_path / "settings.yaml").exists()
    sm = settings_mod.settings_manager
    s = sm.settings
    assert s.logic.discount_percent == 10


@pytest.mark.filterwarnings("ignore:Pydantic serializer warnings:UserWarning:pydantic.main")
def test_malformed_fields_are_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    malformed = """
logic:
  adjustment_factor: 0.85
  min_actual_factor: not_a_number
keys:
  copyitem_key: f9
  unknown_key: foo
currency:
  poe1currencies:
    divine: notint
    chaos: 100
"""
    (tmp_path / "settings.yaml").write_text(malformed)
    with caplog.at_level(logging.WARNING):
        if "poemarcut.settings" in sys.modules:
            del sys.modules["poemarcut.settings"]
        settings_mod = importlib.import_module("poemarcut.settings")
    sm = settings_mod.settings_manager
    s = sm.settings
    # unknown legacy field should be ignored; invalid field kept as default
    assert s.logic.discount_percent == 10
    assert s.logic.max_actual_discount == 50
    # custom key applied
    assert s.keys.copyitem_key == "f9"
    # invalid currency mapping should cause currency section to keep defaults
    assert isinstance(s.currency.poe1currencies, dict)
    assert any("Invalid values in settings.currency" in rec.getMessage() for rec in caplog.records)


def test_currency_delay_validation_suppresses_partial_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.chdir(tmp_path)
    body = """
currency:
  poe1leagues:
    - Mirage
  active_game: 1
  active_league: Mirage
"""
    (tmp_path / "settings.yaml").write_text(body)
    with caplog.at_level(logging.WARNING):
        if "poemarcut.settings" in sys.modules:
            del sys.modules["poemarcut.settings"]
        importlib.import_module("poemarcut.settings")
    # ensure no partial-validation "must be in" warnings were emitted
    assert not any("must be in" in rec.getMessage() for rec in caplog.records)
