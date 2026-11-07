import pytest

from budgetcare.domain.money import format_cents, parse_amount_to_cents


def test_parse_valid_amounts():
    assert parse_amount_to_cents("10") == 1000
    assert parse_amount_to_cents("$10") == 1000
    assert parse_amount_to_cents("10.50") == 1050
    assert parse_amount_to_cents("$10.5") == 1050
    assert parse_amount_to_cents("  $70.25  ") == 7025


def test_parse_invalid_amounts():
    with pytest.raises(ValueError):
        parse_amount_to_cents("0")
    with pytest.raises(ValueError):
        parse_amount_to_cents("$0")
    with pytest.raises(ValueError):
        parse_amount_to_cents("-10")
    with pytest.raises(ValueError):
        parse_amount_to_cents("10.555")
    with pytest.raises(ValueError):
        parse_amount_to_cents("abc")
    with pytest.raises(ValueError):
        parse_amount_to_cents("10,50")


def test_format_cents():
    assert format_cents(1750) == "$17.50"
    assert format_cents(1000) == "$10.00"
    assert format_cents(1000, show_cents=False) == "$10"
    assert format_cents(5) == "$0.05"
