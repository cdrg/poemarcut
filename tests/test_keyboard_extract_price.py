# ruff: noqa: S101
"""Tests for the keyboard.extract_price function.

This module tests the price extraction functionality from keyboard input,
including various price formats and edge cases.
"""

import sys
import types

from poemarcut.keyboard import extract_price

# Inject lightweight dummy modules to avoid importing heavy GUI/OS deps during tests.
for mod_name in ("pyautogui", "pydirectinput", "pyperclip"):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

# Provide a minimal `pynput.keyboard` module with required names.
if "pynput" not in sys.modules:
    pynput_mod = types.ModuleType("pynput")
    keyboard_mod = types.ModuleType("pynput.keyboard")
    keyboard_mod.Key = object  # pyright: ignore[reportAttributeAccessIssue]
    keyboard_mod.KeyCode = object  # pyright: ignore[reportAttributeAccessIssue]
    keyboard_mod.Listener = object  # pyright: ignore[reportAttributeAccessIssue]
    pynput_mod.keyboard = keyboard_mod  # pyright: ignore[reportAttributeAccessIssue]
    sys.modules["pynput"] = pynput_mod
    sys.modules["pynput.keyboard"] = keyboard_mod

# Provide minimal stubs for poemarcut submodules to avoid importing external deps
if "poemarcut.currency" not in sys.modules:
    currency_mod = types.ModuleType("poemarcut.currency")
    currency_mod.get_exchange_rate = lambda: 1.0  # pyright: ignore[reportAttributeAccessIssue]
    sys.modules["poemarcut.currency"] = currency_mod
if "poemarcut.settings" not in sys.modules:
    # Provide a SettingsManager minimal stub used during import (not used by extract_price)
    settings_mod = types.ModuleType("poemarcut.settings")
    settings_mod.SettingsManager = types.SimpleNamespace  # pyright: ignore[reportAttributeAccessIssue]
    sys.modules["poemarcut.settings"] = settings_mod


def test_extract_price_full_text() -> None:
    """Test extraction of price from a sample item description text."""
    sample1 = """Item Class: Heist Gear
Rarity: Rare
Behemoth Apparatus
Aggregator Charm
--------
Any Heist member can equip this item.
--------
Requirements:
Level 4 in Any Job
--------
Item Level: 83
--------
{ Implicit Modifier — Damage, Caster }
23(21-25)% increased Spell Damage (implicit)
--------
{ Prefix Modifier "Masterful" (Tier: 1) — Speed }
19(18-20)% increased Job speed

{ Prefix Modifier "Frosted" (Tier: 4) — Damage, Elemental, Cold }
12(11-15) to 20(18-21) added Cold Damage
Players and their Minions have 12(11-15) to 20(18-21) added Cold Damage

{ Suffix Modifier "of Coordination" (Tier: 2) — Aura }
Grants Level 10 Malevolence Skill

--------
Can only be equipped to Heist members.
--------
Note: ~b/o 90 chaos
"""
    assert extract_price(sample1) == (90, "chaos")
    sample2 = """Item Class: Misc Map Items
Rarity: Normal
Writhing Invitation
--------
Item Level: 83
--------
{ Implicit Modifier }
Modifiers to Item Quantity affect the amount of rewards dropped by the boss (implicit)
--------
The Infinite Hunger awaits in a cosmic stomach where
whole civilisations are digested - but do not die.
--------
Open portals to Seething Chyme by using this item in a personal Map Device.
--------
Note: ~b/o 2,222 whetstone
"""
    assert extract_price(sample2) == (2222, "whetstone")
    sample3 = """Item Class: Maps
Rarity: Rare
Hidden Precinct
Pit of the Chimera Map
--------
Map Tier: 16
Item Quantity: +75% (augmented)
Item Rarity: +32% (augmented)
Monster Pack Size: +21% (augmented)
Quality: +20% (augmented)
--------
Item Level: 82
--------
Monster Level: 83
--------
Delirium Reward Type: Harbinger Items (enchant)
Players in Area are 20% Delirious (enchant)
--------
{ Implicit Modifier }
Area is influenced by The Shaper — Unscalable Value (implicit)
--------
{ Prefix Modifier "Multifarious" (Tier: 1) }
Area has increased monster variety — Unscalable Value

{ Prefix Modifier "Shocking" (Tier: 1) — Damage, Physical, Elemental, Lightning }
Monsters deal 107(90-110)% extra Physical Damage as Lightning

{ Prefix Modifier "Hexwarded" (Tier: 1) — Caster, Curse }
60% less effect of Curses on Monsters

{ Suffix Modifier "of Venom" (Tier: 1) — Chaos, Ailment }
Monsters Poison on Hit — Unscalable Value
(Poison deals Chaos Damage over time, based on the base Physical and Chaos Damage of the Skill. Multiple instances of Poison stack)

--------
Travel to this Map by using it in a personal Map Device. Maps can only be used once.
--------
Note: ~b/o 888 orb-of-binding
"""
    assert extract_price(sample3) == (888, "orb-of-binding")


def test_extract_price_price_only() -> None:
    """Test extraction of price with various formats and edge cases."""
    assert extract_price("~b/o 10 chaos") == (10, "chaos")  # ~b/o
    assert extract_price("~price 1 exalted") == (1, "exalted")  # ~price
    # not currently supporting fractional prices
    # assert extract_price("~b/o 1.9 divine") == (1, "divine")  # noqa: ERA001
    assert extract_price("~b/o 1,000 chaos") == (1000, "chaos")  # US thousands separator
    assert extract_price("~b/o 1.000 chaos") == (1000, "chaos")  # EU thousands separator


def test_no_price_found() -> None:
    """Test extraction when no price is found in the text."""
    assert extract_price("No price here") == (None, None)
