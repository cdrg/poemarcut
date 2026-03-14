"""Item-related functionality for PoEMarcut.

Defines simple, serializable dataclasses for items, mods, and notes
used by the rest of the application.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass
class Item:
    """Represents a Path of Exile 1 or 2 item."""

    @dataclass
    class Mod:
        """Represents a single item mod.

        Attributes:
            name: Short identifier for the mod (e.g. "+# to Strength").
            text: Full mod text as shown on the item.
            value: Numeric value extracted from the mod (if any) or None.

        """

        name: str
        text: str
        value: float | None = None

    @dataclass
    class Note:
        """Represents a note attached to an item (trade note).

        Attributes:
            text: The full note text (for example "~b/o 2 chaos").
            price: Integer price parsed from the note or None.
            currency: Currency type string id (e.g. "chaos") or None.

        """

        text: str
        price: int | None = None
        currency: str | None = None

    class Rarity(Enum):
        """Enumeration of supported item rarities."""

        UNIQUE = "Unique"
        RARE = "Rare"
        MAGIC = "Magic"
        COMMON = "Common"

    name: str
    basetype: str
    class_: str = ""
    rarity: Rarity | None = None
    requirements: dict[str, int] = field(default_factory=dict)
    item_level: int | None = None
    droplevel: int | None = None
    enchantments: list[str] = field(default_factory=list)
    implicit_mods: list[Mod] = field(default_factory=list)
    explicit_mods: list[Mod] = field(default_factory=list)
    note: Note | None = None

    def add_implicit(self, mod: Mod) -> None:
        """Add an implicit mod to the item.

        Args:
            mod (Item.Mod): The implicit mod to append.

        Returns:
            None

        """
        self.implicit_mods.append(mod)

    def add_explicit(self, mod: Mod) -> None:
        """Add an explicit mod to the item.

        Args:
            mod (Item.Mod): The explicit mod to append.

        Returns:
            None

        """
        self.explicit_mods.append(mod)

    def to_dict(self) -> dict[str, Any]:
        """Serialize item to a plain dictionary.

        Useful for logging or JSON serialization.

        Returns:
            dict[str, Any]: A plain-serializable mapping of item attributes.

        """
        return {
            "rarity": self.rarity.value if self.rarity is not None else None,
            "name": self.name,
            "basetype": self.basetype,
            "class": self.class_,
            "requirements": dict(self.requirements),
            "item_level": self.item_level,
            "droplevel": self.droplevel,
            "enchantments": list(self.enchantments),
            "implicit_mods": [m.__dict__ for m in self.implicit_mods],
            "explicit_mods": [m.__dict__ for m in self.explicit_mods],
            "note": self.note.__dict__ if self.note is not None else None,
        }

    @classmethod
    def from_text(cls, text: str) -> "Item":  # noqa: C901, PLR0912, PLR0915
        """Create an Item by parsing raw copied item text.

        This implements a minimal, forgiving parser sufficient for tests
        and basic workflows: it extracts `class_`, `rarity`, `name`,
        `basetype`, `item_level`, `droplevel` (map tier), simple
        `requirements` (level), and the trade `note` (with price/currency).

        Args:
            text (str): Raw item text copied from the game or clipboard.

        Returns:
            Item: Parsed Item instance.

        """
        lines_raw = text.splitlines()
        lines = [raw.strip() for raw in lines_raw if raw.strip()]

        class_ = ""
        rarity = None
        name = ""
        basetype = ""
        item_level = None
        droplevel = None
        requirements: dict[str, int] = {}
        note_obj = None

        # Helper to map rarity string to enum
        def _map_rarity(rarity_str: str) -> "Item.Rarity | None":
            """Map a rarity string to the `Item.Rarity` enum.

            Args:
                rarity_str (str): The rarity string parsed from item text.

            Returns:
                Item.Rarity | None: Matching enum member or None if unknown.

            """
            if not rarity_str:
                return None
            lr = rarity_str.strip().lower()
            if lr == "normal":
                return cls.Rarity.COMMON
            for r in cls.Rarity:
                if r.value.lower() == lr:
                    return r
            return None

        # Find simple key/value lines and indices
        for idx, line in enumerate(lines):
            low = line.lower()
            if low.startswith("item class:"):
                class_ = line.split(":", 1)[1].strip()
            elif low.startswith("rarity:"):
                rarity = _map_rarity(line.split(":", 1)[1].strip())
                # Collect following name/basetype lines until a separator or key-like line
                j = idx + 1
                name_lines: list[str] = []
                while j < len(lines):
                    nxt = lines[j]
                    if nxt.startswith("--------") or ":" in nxt:
                        break
                    if nxt.startswith("{"):
                        break
                    name_lines.append(nxt)
                    j += 1
                if name_lines:
                    name = name_lines[0]
                    if len(name_lines) > 1:
                        basetype = name_lines[1]
            elif low.startswith("item level:"):
                m = re.search(r"(\d+)", line)
                if m:
                    item_level = int(m.group(1))
            elif low.startswith("map tier"):
                m = re.search(r"(\d+)", line)
                if m:
                    droplevel = int(m.group(1))
            elif low.startswith("requirements:"):
                # scan subsequent lines until separator
                j = idx + 1
                while j < len(lines) and not lines[j].startswith("--------"):
                    lvl_m = re.search(r"level\s*(\d+)", lines[j], flags=re.IGNORECASE)
                    if lvl_m:
                        requirements["level"] = int(lvl_m.group(1))
                    j += 1
            elif low.startswith("note:"):
                note_text = line.split(":", 1)[1].strip()
                # Inline price extraction to keep parsing logic local to Item
                pattern = r"~\s*(?:b/o|price)\b[:\s]*([\d\.,]+)\s*([A-Za-z0-9]+(?:[-\s][A-Za-z0-9]+)*)"
                m = re.search(pattern, line, flags=re.IGNORECASE)
                if m:
                    price_str, cur_type = m.groups()
                    normalized = price_str.replace(",", "").replace(".", "").replace(" ", "")
                    try:
                        price_val = int(normalized)
                    except ValueError:
                        price_val, cur_type = None, None
                    else:
                        cur_type = cur_type.lower().strip()
                else:
                    price_val, cur_type = None, None

                note_obj = cls.Note(text=note_text, price=price_val, currency=cur_type)

        # Fallback: if name empty, try first non-key line
        if not name:
            for line in lines:
                if ":" not in line and not line.startswith("--------") and not line.startswith("{"):
                    name = line
                    break

        return cls(
            name=name,
            basetype=basetype,
            class_=class_,
            rarity=rarity,
            requirements=requirements,
            item_level=item_level,
            droplevel=droplevel,
            note=note_obj,
        )
