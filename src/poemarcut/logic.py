"""Pure logic helpers extracted from keyboard handling.

These helpers encapsulate parsing, discount computation, and currency
conversion logic so they can be unit-tested independently of keyboard
interactions and side effects.
"""

import math
from collections.abc import Callable


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


def _compute_minimum_price(  # noqa: PLR0911, PLR0913
    original_units: int,
    current_currency: str | None,
    currencies: list[str],
    minimum_discount: int,
    minimum_discount_currency: str,
    get_exchange_rate: Callable[..., float],
) -> tuple[int | None, str | None, float] | None:
    """Compute the adjusted price required to satisfy a minimum currency discount.

    Returns the discounted price in the appropriate currency and the observed
    actual discount percent relative to that currency's original price.
    """
    if minimum_discount <= 0:
        return None

    if not current_currency or current_currency not in currencies:
        return None
    if minimum_discount_currency not in currencies:
        return None

    currencies_list = list(currencies)
    units = float(original_units)

    try:
        if current_currency == minimum_discount_currency:
            min_amount_current = float(minimum_discount)
        else:
            min_amount_current = float(minimum_discount) * get_exchange_rate(
                from_currency=minimum_discount_currency,
                to_currency=current_currency,
            )
    except (LookupError, KeyError, ValueError, TypeError):
        return None

    target = units - min_amount_current
    idx = currencies_list.index(current_currency)
    rate_conversion = 1.0

    while True:
        if target >= 1.0 - 1e-9:
            price = math.floor(target + 1e-9)
            price = max(price, 1)
            original_price_in_curr = units * rate_conversion
            actual = (original_price_in_curr - price) * 100.0 / original_price_in_curr
            return price, current_currency, actual

        if idx == len(currencies_list) - 1:
            original_price_in_curr = units * rate_conversion
            price = 1
            actual = (original_price_in_curr - 1) * 100.0 / original_price_in_curr
            return price, currencies_list[-1], actual

        next_currency = currencies_list[idx + 1]
        try:
            rate = get_exchange_rate(from_currency=current_currency, to_currency=next_currency)
        except (LookupError, KeyError, ValueError, TypeError):
            return None

        rate_conversion *= float(rate)
        target *= float(rate)
        current_currency = next_currency
        idx += 1


def convert_and_compute_price(  # noqa: C901, PLR0911, PLR0912, PLR0913
    original_units: int,
    last_cur_type: str | None,
    currencies: list[str],
    discount_percent: int,
    max_actual_discount: int,
    get_exchange_rate: Callable[..., float],
    minimum_discount: int | None = None,
    minimum_discount_currency: str | None = None,
) -> tuple[int | None, str | None, float]:
    """Convert down the currency chain to find a valid discounted price.

    Attempt conversions until a price can be computed that respects
    `max_actual_discount` while applying at least `discount_percent` when
    possible.

    If `minimum_discount` is specified, the returned price will also satisfy
    the configured minimum currency discount. If the requested percentage
    discount already satisfies the minimum, it is used directly. Otherwise the
    minimum discount result is chosen, and it may override `max_actual_discount`
    when they conflict.

    Args:
        original_units: number of units in the original currency (e.g. 2 divines)
        last_cur_type: the original currency type string
        currencies: ordered list of currencies from highest to lowest
        discount_percent: minimum discount percent to apply
        max_actual_discount: maximum allowed actual discount percent
        get_exchange_rate: callable used to fetch exchange rates. Signature
            should accept keyword args `from_currency` and `to_currency` and
            return a float rate.
        minimum_discount: optional minimum discount amount to apply
        minimum_discount_currency: optional currency type for minimum discount

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

    min_candidate: tuple[int | None, str | None, float] | None = None
    if minimum_discount is not None and minimum_discount_currency is not None:
        min_candidate = _compute_minimum_price(
            original_units=original_units,
            current_currency=current_currency,
            currencies=currencies_list,
            minimum_discount=minimum_discount,
            minimum_discount_currency=minimum_discount_currency,
            get_exchange_rate=get_exchange_rate,
        )

    # initial price in the same currency
    price = units
    discounted, actual = _calc(price, discount_percent)
    if actual <= float(max_actual_discount):
        if min_candidate is None:
            return discounted, current_currency, actual
        min_discounted, min_currency, min_actual = min_candidate
        if min_actual > actual:
            return min_discounted, min_currency, min_actual
        return discounted, current_currency, actual

    # If the preferred discount is too high due to integer rounding,
    # fall back to the configured maximum allowed actual discount.
    if discount_percent != max_actual_discount:
        discounted, actual = _calc(price, max_actual_discount)
        if actual <= float(max_actual_discount):
            if min_candidate is None:
                return discounted, current_currency, actual
            min_discounted, min_currency, min_actual = min_candidate
            if min_actual > actual:
                return min_discounted, min_currency, min_actual
            return discounted, current_currency, actual

    # If the percentage logic could not satisfy the min/max constraints,
    # the configured minimum discount takes precedence when available.
    if min_candidate is not None:
        return min_candidate

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
        except (LookupError, KeyError, ValueError, TypeError):
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
