import re

import pytest

from poemarcut import constants
from poemarcut.util import (
    shortest_unique_prefix,
    shortest_unique_prefixes_in_order,
)


def test_shortest_unique_prefix_basic() -> None:
    items = ["dog", "deer", "deal"]
    prefixes = shortest_unique_prefixes_in_order(items)
    assert prefixes == ["d", "de", "dea"]
    assert shortest_unique_prefix("deal", items) == "dea"


def test_shortest_unique_prefix_not_found_raises() -> None:
    with pytest.raises(ValueError, match="target_string not found in string_list"):
        shortest_unique_prefix("cat", ["dog", "deer"])


def test_prefixes_in_order_consistency() -> None:
    items = ["apple", "apricot", "banana", "apple"]
    prefixes = shortest_unique_prefixes_in_order(items)
    assert len(prefixes) == len(items)
    for i, s in enumerate(items):
        # each returned prefix must match the per-item computation
        assert prefixes[i] == shortest_unique_prefix(s, items)


def _normalize_names(names: list[str]) -> list[str]:
    # lower-case and remove any non-alphanumeric characters to match
    # how the constants prefixes were computed
    return [re.sub(r"[^a-z0-9]", "", n.lower()) for n in names]


def test_constants_prefixes_match_computed_poe1_and_poe2() -> None:
    # POE1
    poe1_names = list(constants.POE1_MERCHANT_CURRENCIES.values())
    poe1_normalized = _normalize_names(poe1_names)
    computed_poe1 = shortest_unique_prefixes_in_order(poe1_normalized)
    expected_poe1 = [constants.POE1_MERCHANT_CURRENCY_PREFIXES[k] for k in constants.POE1_MERCHANT_CURRENCIES]
    assert computed_poe1 == expected_poe1, "POE1 precomputed prefixes disagree with computed prefixes"

    # POE2
    poe2_names = list(constants.POE2_MERCHANT_CURRENCIES.values())
    poe2_normalized = _normalize_names(poe2_names)
    computed_poe2 = shortest_unique_prefixes_in_order(poe2_normalized)
    expected_poe2 = [constants.POE2_MERCHANT_CURRENCY_PREFIXES[k] for k in constants.POE2_MERCHANT_CURRENCIES]
    assert computed_poe2 == expected_poe2, "POE2 precomputed prefixes disagree with computed prefixes"
