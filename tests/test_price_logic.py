import pytest

from poemarcut import item, logic


def test_parse_int_price_valid() -> None:
    assert item.parse_int_price("1,234") == 1234
    assert item.parse_int_price("1.234") == 1234
    assert item.parse_int_price("42") == 42


def test_parse_int_price_invalid() -> None:
    with pytest.raises(ValueError, match=r"invalid literal|could not convert|invalid price|valid integer"):
        item.parse_int_price("abc")


def test_compute_discounted_price_and_actual() -> None:
    discounted, actual = logic.compute_discounted_price_and_actual(100, 10)
    assert discounted == 90
    assert pytest.approx(actual, rel=1e-9) == 10.0


def test_compute_discount_minimum() -> None:
    # discount_percent is a minimum; for price 12 and 10% the
    # absolute discount should be ceil(1.2)=2 -> discounted price 10
    discounted, actual = logic.compute_discounted_price_and_actual(12, 10)
    assert discounted == 10
    assert pytest.approx(actual, rel=1e-9) == pytest.approx(2 * 100.0 / 12, rel=1e-9)


def test_next_currency_if_needed() -> None:
    currencies = ["a", "b", "c"]
    # price 1 forces conversion
    assert logic.next_currency_if_needed(1, 0.0, 5, "a", currencies) == "b"
    # excessive actual discount forces conversion
    assert logic.next_currency_if_needed(10, 10.0, 5, "a", currencies) == "b"
    # no conversion when not needed
    assert logic.next_currency_if_needed(10, 2.0, 5, "a", currencies) is None


def test_max_actual_discount_precedence_after_conversion() -> None:
    # If applying the minimum `discount_percent` would yield an actual
    # discount larger than `max_actual_discount`, after converting to the
    # next currency the max should be used. Example: 2 divine -> 2*270
    # chaos, max_actual_discount 40% -> expected price 540*(1-0.4)=324
    last_price = 2
    exchange_rate = 270
    converted_price = int(last_price * exchange_rate)
    discounted, actual = logic.compute_discounted_price_and_actual(converted_price, 40)
    assert discounted == 324
    assert pytest.approx(actual, rel=1e-9) == 40.0


def test_conversion_chain_with_low_first_rate_succeeds() -> None:
    # First-step rate is low (1.1) so a single conversion doesn't help,
    # but converting a second time should produce a price where the
    # preferred discount can be applied within max_actual_discount.
    currencies = ["divine", "annul", "chaos"]
    rates = {
        ("divine", "annul"): 1.1,
        ("annul", "chaos"): 150.0,
    }

    def get_rate(*, from_currency: str, to_currency: str) -> float:
        return rates[(from_currency, to_currency)]

    discounted, cur, actual = logic.convert_and_compute_price(
        original_units=2,
        last_cur_type="divine",
        currencies=currencies,
        discount_percent=10,
        max_actual_discount=40,
        get_exchange_rate=get_rate,
    )

    # After two-step conversion (1.1 * 150 = 165) price = 2*165=330 and
    # preferred 10% discount yields discounted price 297.
    assert discounted == 297
    assert cur == "chaos"
    assert pytest.approx(actual, rel=1e-9) == 10.0


def test_conversion_chain_with_impossible_low_max_fails() -> None:
    # If max_actual_discount is very small and no conversion path can
    # achieve it, the helper should return (None, None, last_actual).
    currencies = ["a", "b"]

    def get_rate(*, from_currency: str, to_currency: str) -> float:  # noqa: ARG001
        # conversion doesn't change value materially
        return 1.0

    discounted, cur, actual = logic.convert_and_compute_price(
        original_units=2,
        last_cur_type="a",
        currencies=currencies,
        discount_percent=5,
        max_actual_discount=1,  # very low max -> likely impossible
        get_exchange_rate=get_rate,
    )

    assert discounted is None
    assert cur is None
    assert actual > 1.0


def test_convert_and_compute_handles_lookuperror_from_get_rate() -> None:
    """If the exchange-rate callable raises LookupError, the helper should gracefully return (None, None, last_actual) rather than raising.

    This prevents errors from currency lookups (e.g. network/cache issues) from bubbling out of higher-level callers.
    """
    currencies = ["divine", "chaos"]

    def get_rate(*, from_currency: str, to_currency: str) -> float:  # noqa: ARG001
        msg = "no data"
        raise LookupError(msg)

    # Choose parameters so initial actual discount is larger than max_actual
    # to force the function to attempt a conversion and call get_rate.
    discounted, cur, actual = logic.convert_and_compute_price(
        original_units=2,
        last_cur_type="divine",
        currencies=currencies,
        discount_percent=50,
        max_actual_discount=10,
        get_exchange_rate=get_rate,
    )

    assert discounted is None
    assert cur is None
    # initial actual for 2 units with 50% should be 50.0
    assert pytest.approx(actual, rel=1e-9) == 50.0
