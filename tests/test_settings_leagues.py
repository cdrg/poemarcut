from pathlib import Path

import pytest
from yaml import SafeDumper, SafeLoader, dump, load

from poemarcut import settings as settings_mod


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        dump(data, f, sort_keys=False, Dumper=SafeDumper)


def test_set_settings_does_not_persist_empty_leagues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Use a temp settings file
    settings_file = tmp_path / "settings.yaml"
    monkeypatch.setattr(settings_mod, "SETTINGS_FILE", settings_file)

    mgr = settings_mod.SettingsManager()
    current = mgr.settings

    # Build a PoEMSettings instance that (incorrectly) has empty league lists
    bad_currency = current.currency.model_dump()
    bad_currency["poe1leagues"] = []
    bad_currency["poe2leagues"] = []

    bad_currency_inst = settings_mod.CurrencySettings.model_construct(**bad_currency)
    bad = settings_mod.PoEMSettings.model_construct(keys=current.keys, logic=current.logic, currency=bad_currency_inst)

    mgr.set_settings(bad)

    # Read back the YAML and ensure leagues were not persisted empty
    with settings_file.open() as f:
        persisted = load(f, Loader=SafeLoader)

    currency = persisted.get("currency", {}) or {}
    p1 = currency.get("poe1leagues")
    p2 = currency.get("poe2leagues")

    assert p1, "poe1leagues must not be persisted empty"
    assert p2, "poe2leagues must not be persisted empty"


def test_load_corrects_empty_leagues_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Create a settings YAML that contains empty league lists
    settings_file = tmp_path / "settings.yaml"
    monkeypatch.setattr(settings_mod, "SETTINGS_FILE", settings_file)

    data = {
        "keys": {},
        "logic": {},
        "currency": {
            "poe1leagues": [],
            "poe2leagues": [],
            "poe1currencies": {"divine": 1, "chaos": 100},
            "poe2currencies": {"divine": 1, "chaos": 30, "exalted": 240},
            "active_game": 1,
            "active_league": "tmpstandard",
        },
    }

    write_yaml(settings_file, data)

    mgr = settings_mod.SettingsManager()
    s = mgr.settings

    # For active_game==1, poe1leagues should have been corrected to include active_league
    assert s.currency.poe1leagues, "poe1leagues should be corrected on load"
    assert s.currency.active_league in s.currency.poe1leagues
    # poe2leagues should also be non-empty (defaults)
    assert s.currency.poe2leagues
