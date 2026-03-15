import pytest

from poemarcut import logic


def test_parse_int_price_valid() -> None:
    assert logic.parse_int_price("1,234") == 1234
    assert logic.parse_int_price("1.234") == 1234
    assert logic.parse_int_price("42") == 42


def test_parse_int_price_invalid() -> None:
    with pytest.raises(ValueError, match=r"invalid literal|could not convert|invalid price|valid integer"):
        logic.parse_int_price("abc")


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
