import re

AMOUNT_REGEX = re.compile(r"^\$?\s*(\d{1,7})(?:\.(\d{1,2}))?$")


def parse_amount_to_cents(amount_str: str) -> int:
    """Parse a dollar amount string into integer cents.

    Accepts: '10', '$10', '10.50', '10.5'.
    Rejects: zero, negative, more than 2 decimal places, invalid characters.
    """
    cleaned = amount_str.strip()
    match = AMOUNT_REGEX.match(cleaned)
    if not match:
        raise ValueError(f"Invalid amount format: {amount_str}")

    dollars_part = match.group(1)
    cents_part = match.group(2) or ""

    dollars = int(dollars_part)
    cents = int(cents_part.ljust(2, "0")) if cents_part else 0
    total_cents = dollars * 100 + cents

    if total_cents <= 0:
        raise ValueError("Amount must be greater than zero.")

    return total_cents


def format_cents(cents: int, show_cents: bool = True) -> str:
    """Format integer cents into a dollar string, e.g. 1750 -> '$17.50'."""
    dollars = cents // 100
    remainder = cents % 100
    if remainder == 0 and not show_cents:
        return f"${dollars}"
    return f"${dollars}.{remainder:02d}"
