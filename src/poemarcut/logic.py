"""Pure logic helpers extracted from keyboard handling.

These helpers encapsulate parsing, discount computation, and currency
conversion logic so they can be unit-tested independently of keyboard
interactions and side effects.
"""

import math


def parse_int_price(raw: str) -> int:
    """Parse a clipboard/raw string into an integer price.

    Removes common thousands separators (comma and dot) and converts to
    int. Raises ValueError on invalid input.
    """
    s = (raw or "").replace(",", "").replace(".", "")
    try:
        return int(s)
    except (ValueError, TypeError) as e:
        msg = f"Clipboard value '{raw}' is not a valid integer"
        raise ValueError(msg) from e


def compute_discounted_price_and_actual(copied_price: int, discount_percent: int) -> tuple[int, float]:
    """Return (discounted_price, actual_discount_percent).

    The `discount_percent` value is treated as a minimum required
    discount. The function computes the integer discount amount as the
    smallest integer number of currency units that yields an actual
    discount percent >= `discount_percent` (i.e. ceiling of the exact
    discount amount). The returned actual discount is the observed
    percent after integer rounding.
    """
    if copied_price <= 0:
        msg = "copied_price must be > 0"
        raise ValueError(msg)
    # compute absolute discount amount and round up so the resulting percent is at least discount_percent
    exact_discount = copied_price * (float(discount_percent) / 100.0)
    discount_amount = math.ceil(exact_discount)
    discounted = copied_price - discount_amount
    actual = (copied_price - discounted) * 100.0 / copied_price
    return discounted, actual


def next_currency_if_needed(
    copied_price: int,
    actual_discount: float,
    max_actual_discount: int,
    last_cur_type: str | None,
    currencies: list[str],
) -> str | None:
    """Decide whether to convert to the next currency.

    Returns the next currency type string if conversion should occur,
    otherwise ``None``.
    """
    if (
        (copied_price == 1 or actual_discount > float(max_actual_discount))
        and last_cur_type
        and last_cur_type in currencies
        and last_cur_type != currencies[-1]
    ):
        idx = currencies.index(last_cur_type)
        return currencies[idx + 1]
    return None
