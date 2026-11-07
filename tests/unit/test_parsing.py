import pytest

from budgetcare.bot.parsing import parse_amount


def test_parse_amount_valid():
    assert parse_amount("10") == 1000
    assert parse_amount("$10") == 1000
    assert parse_amount("10.50") == 1050
    assert parse_amount("10.5") == 1050
    assert parse_amount("  $100.25  ") == 10025


def test_parse_amount_invalid():
    with pytest.raises(ValueError, match="Invalid amount format"):
        parse_amount("abc")
    with pytest.raises(ValueError, match="Invalid amount format"):
        parse_amount("10.555")
    with pytest.raises(ValueError, match="Invalid amount format"):
        parse_amount("10,50")
    with pytest.raises(ValueError, match="must be greater than"):
        parse_amount("0")
    with pytest.raises(ValueError, match="exceeds maximum"):
        parse_amount("2000000", max_cents=100_000_000)
