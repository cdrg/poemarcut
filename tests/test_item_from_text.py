# ruff: noqa: S101
"""Tests for `Item.from_text` price extraction from item note.

Verifies parsing of various price formats and edge cases.
"""

from poemarcut.item import Item


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
    item = Item.from_text(sample1)
    assert item.note is not None
    assert item.note.price == 90
    assert item.note.currency == "chaos"
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
    item = Item.from_text(sample2)
    assert item.note is not None
    assert item.note.price == 2222
    assert item.note.currency == "whetstone"
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
    item = Item.from_text(sample3)
    assert item.note is not None
    assert item.note.price == 888
    assert item.note.currency == "orb-of-binding"


def test_extract_price_price_only() -> None:
    """Test extraction of price with various formats and edge cases."""
    item = Item.from_text("Note: ~b/o 10 chaos")
    assert item.note is not None
    assert item.note.price == 10
    assert item.note.currency == "chaos"

    item = Item.from_text("Note: ~price 1 exalted")
    assert item.note is not None
    assert item.note.price == 1
    assert item.note.currency == "exalted"
    # not currently supporting fractional prices
    # assert extract_price("~b/o 1.9 divine") == (1, "divine")  # noqa: ERA001
    item = Item.from_text("Note: ~b/o 1,000 chaos")
    assert item.note is not None
    assert item.note.price == 1000
    assert item.note.currency == "chaos"

    item = Item.from_text("Note: ~b/o 1.000 chaos")
    assert item.note is not None
    assert item.note.price == 1000
    assert item.note.currency == "chaos"


def test_no_price_found() -> None:
    """Test extraction when no price is found in the text."""
    item = Item.from_text("Note: No price here")
    assert item.note is not None
    assert item.note.price is None
    assert item.note.currency is None
