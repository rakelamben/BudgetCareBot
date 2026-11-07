from budgetcare.domain.models import MoodTier


def calculate_condition(missed_periods: int, total_feedings: int) -> int:
    """Calculate condition percentage (0-100), rounded down.

    100% appears only when nothing was missed (missed_periods == 0).
    """
    if total_feedings <= 0:
        return 100
    if missed_periods <= 0:
        return 100
    if missed_periods >= total_feedings:
        return 0
    on_time = total_feedings - missed_periods
    condition = (on_time * 100) // total_feedings
    return max(0, min(100, condition))


def calculate_mood_tier(missed_periods: int, total_feedings: int) -> MoodTier:
    """Determine mood tier (1-4) based on condition boundaries.

    Tier 4: 0 misses (100%)
    Tier 3: condition >= 75%
    Tier 2: condition >= 50%
    Tier 1: condition < 50% (and below 25% keeps tier 1)
    """
    if total_feedings <= 0 or missed_periods == 0:
        return MoodTier.TIER_4

    n = total_feedings
    m = missed_periods
    on_time = n - m

    if on_time * 100 >= 75 * n:
        return MoodTier.TIER_3
    elif on_time * 100 >= 50 * n:
        return MoodTier.TIER_2
    else:
        return MoodTier.TIER_1


def calculate_live_service_quality(
    deposited_cents: int,
    target_cents: int,
    days_elapsed: int,
    period_days: int,
) -> float:
    """Calculate live service quality [0.0, 1.0].

    Live view is pace-based: deposited / (target * care_period).
    Shown as 1.0 (100%) while care period is 0 (per PRD 8.5).
    """
    if target_cents <= 0 or period_days <= 0:
        return 1.0

    clamped_days = max(0, min(days_elapsed, period_days))
    if clamped_days == 0:
        return 1.0

    care_period = clamped_days / period_days
    expected_cents = target_cents * care_period
    if expected_cents <= 0:
        return 1.0

    quality = deposited_cents / expected_cents
    return min(1.0, max(0.0, quality))


def calculate_final_service_quality(deposited_cents: int, target_cents: int) -> float:
    """Calculate final service quality: deposited / target, capped at 1.0."""
    if target_cents <= 0:
        return 1.0
    return min(1.0, max(0.0, deposited_cents / target_cents))


def calculate_surplus(deposited_cents: int, target_cents: int) -> int:
    """Calculate surplus cents above target."""
    return max(0, deposited_cents - target_cents)


def get_result_title(outcome: str, mood_tier: MoodTier) -> str:
    """Return result screen title based on outcome and mood tier."""
    if outcome.lower() == "graduated":
        if mood_tier == MoodTier.TIER_4:
            return "Well cared for"
        elif mood_tier == MoodTier.TIER_3:
            return "Cared for"
        elif mood_tier == MoodTier.TIER_2:
            return "Made it through"
        else:
            return "Struggled but made it"
    else:  # expired
        if mood_tier in (MoodTier.TIER_4, MoodTier.TIER_3):
            return "Almost there"
        else:
            return "Needs another try"
