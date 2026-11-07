import re

AMOUNT_PATTERN = re.compile(r"^\$?\s*(\d{1,7})(?:\.(\d{1,2}))?$")


def parse_amount(raw: str, max_cents: int = 100_000_000) -> int:
    """Parse and validate amount string from user input into integer cents.

    Raises ValueError with descriptive reason on failure.
    """
    text = raw.strip()
    match = AMOUNT_PATTERN.match(text)
    if not match:
        raise ValueError(
            "Invalid amount format. Please enter a valid dollar amount (e.g., 10, $10, 10.50)."
        )

    dollars_str = match.group(1)
    cents_str = match.group(2) or ""

    dollars = int(dollars_str)
    cents = int(cents_str.ljust(2, "0")) if cents_str else 0
    total_cents = dollars * 100 + cents

    if total_cents <= 0:
        raise ValueError("Amount must be greater than $0.")

    if total_cents > max_cents:
        raise ValueError(f"Amount exceeds maximum allowed limit of ${max_cents // 100:,}.")

    return total_cents


def parse_amount_to_cents(raw: str, allow_zero: bool = True) -> int | None:
    """Parse raw amount string into integer cents, returning None if invalid.

    Allows 0 (free food) if allow_zero=True.
    """
    text = raw.strip()
    if allow_zero and text in ("0", "$0", "0.0", "0.00"):
        return 0

    try:
        return parse_amount(text)
    except ValueError:
        return None
