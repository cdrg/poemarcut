"""Pure logic helpers extracted from keyboard handling.

These helpers encapsulate parsing, discount computation, and currency
conversion logic so they can be unit-tested independently of keyboard
interactions and side effects.
"""

import math
from collections.abc import Callable


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


def convert_and_compute_price(  # noqa: C901, PLR0911, PLR0913
    original_units: int,
    last_cur_type: str | None,
    currencies: list[str],
    discount_percent: int,
    max_actual_discount: int,
    get_exchange_rate: Callable[..., float],
) -> tuple[int | None, str | None, float]:
    """Convert down the currency chain to find a valid discounted price.

    Attempt conversions until a price can be computed that respects
    `max_actual_discount` while applying at least `discount_percent` when
    possible.

    Args:
        original_units: number of units in the original currency (e.g. 2 divines)
        last_cur_type: the original currency type string
        currencies: ordered list of currencies from highest to lowest
        discount_percent: minimum discount percent to apply
        max_actual_discount: maximum allowed actual discount percent
        get_exchange_rate: callable used to fetch exchange rates. Signature
            should accept keyword args `from_currency` and `to_currency` and
            return a float rate.

    Returns:
        A tuple (discounted_price_or_None, final_currency_or_None, actual_percent)
        If no satisfactory conversion exists the first two elements are None
        and `actual_percent` contains the last observed actual discount.

    """
    if original_units <= 0:
        msg = "original_units must be > 0"
        raise ValueError(msg)

    # Helper to compute discount and actual percent for a given integer price
    def _calc(price: int, percent: int) -> tuple[int, float]:
        return compute_discounted_price_and_actual(price, percent)

    # Start with no conversion
    current_currency = last_cur_type
    currencies_list = list(currencies)
    # Use original units when converting down the chain so rounding doesn't
    # compound across steps.
    units = int(original_units)
    cumulative_rate = 1.0

    # initial price in the same currency
    price = units
    discounted, actual = _calc(price, discount_percent)
    if actual <= float(max_actual_discount):
        return discounted, current_currency, actual

    # If the preferred discount is too high due to integer rounding,
    # fall back to the configured maximum allowed actual discount.
    if discount_percent != max_actual_discount:
        discounted, actual = _calc(price, max_actual_discount)
        if actual <= float(max_actual_discount):
            return discounted, current_currency, actual

    # Try converting down the chain until we either succeed or run out of
    # currencies.
    if not current_currency or current_currency not in currencies_list:
        return None, None, actual

    idx = currencies_list.index(current_currency)
    while idx < len(currencies_list) - 1:
        next_idx = idx + 1
        next_currency = currencies_list[next_idx]
        try:
            rate = get_exchange_rate(from_currency=current_currency, to_currency=next_currency)
        except (KeyError, ValueError, TypeError):
            return None, None, actual

        cumulative_rate *= float(rate)
        price = int(units * cumulative_rate)

        if price <= 0:
            current_currency = next_currency
            idx = next_idx
            continue

        # Try preferred discount first for this converted price.
        discounted, actual = _calc(price, discount_percent)

        # If the computed actual is within the allowed maximum, we're done.
        if actual <= float(max_actual_discount):
            return discounted, next_currency, actual

        # Otherwise, try using max allowed actual discount as fallback.
        if discount_percent != max_actual_discount:
            discounted, actual = _calc(price, max_actual_discount)
            if actual <= float(max_actual_discount):
                return discounted, next_currency, actual

        # advance to next currency in chain
        current_currency = next_currency
        idx = next_idx

    # exhausted conversion chain without finding a satisfactory price
    return None, None, actual
