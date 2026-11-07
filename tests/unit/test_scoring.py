from budgetcare.domain.models import MoodTier
from budgetcare.domain.scoring import (
    calculate_condition,
    calculate_final_service_quality,
    calculate_live_service_quality,
    calculate_mood_tier,
    calculate_surplus,
    get_result_title,
)


def test_condition_and_mood_tiers():
    # Acceptance Criterion 8.5:
    # Given a goal with 4 feedings and one missed cut-off, then condition is 75%.
    assert calculate_condition(missed_periods=1, total_feedings=4) == 75
    assert calculate_mood_tier(missed_periods=1, total_feedings=4) == MoodTier.TIER_3

    # 0 misses gives 100% and Tier 4
    assert calculate_condition(missed_periods=0, total_feedings=4) == 100
    assert calculate_mood_tier(missed_periods=0, total_feedings=4) == MoodTier.TIER_4

    # 2 misses of 4 gives 50% and Tier 2
    assert calculate_condition(missed_periods=2, total_feedings=4) == 50
    assert calculate_mood_tier(missed_periods=2, total_feedings=4) == MoodTier.TIER_2

    # 3 misses of 4 gives 25% and Tier 1
    assert calculate_condition(missed_periods=3, total_feedings=4) == 25
    assert calculate_mood_tier(missed_periods=3, total_feedings=4) == MoodTier.TIER_1

    # 4 misses of 4 gives 0% and Tier 1 (never dies)
    assert calculate_condition(missed_periods=4, total_feedings=4) == 0
    assert calculate_mood_tier(missed_periods=4, total_feedings=4) == MoodTier.TIER_1


def test_live_service_quality():
    # Acceptance Criterion 8.5:
    # Given a $70 goal over 28 days, when 14 days have passed with $35 deposited,
    # then live service quality is 100%.
    quality = calculate_live_service_quality(
        deposited_cents=3500,
        target_cents=7000,
        days_elapsed=14,
        period_days=28,
    )
    assert quality == 1.0

    # Day 0: care period is 0 -> live quality is 100% (1.0)
    assert calculate_live_service_quality(0, 7000, 0, 28) == 1.0

    # Behind pace: 14 days passed, deposited $17.50 of expected $35.00 -> 50%
    assert calculate_live_service_quality(1750, 7000, 14, 28) == 0.5


def test_surplus_and_final_quality():
    # Target $70 (7000 cents), deposited $80 (8000 cents)
    assert calculate_final_service_quality(8000, 7000) == 1.0
    assert calculate_surplus(8000, 7000) == 1000  # $10 surplus


def test_result_titles():
    assert get_result_title("graduated", MoodTier.TIER_4) == "Well cared for"
    assert get_result_title("graduated", MoodTier.TIER_3) == "Cared for"
    assert get_result_title("graduated", MoodTier.TIER_2) == "Made it through"
    assert get_result_title("graduated", MoodTier.TIER_1) == "Struggled but made it"

    assert get_result_title("expired", MoodTier.TIER_3) == "Almost there"
    assert get_result_title("expired", MoodTier.TIER_1) == "Needs another try"
