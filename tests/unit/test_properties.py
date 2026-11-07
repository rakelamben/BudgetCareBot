from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from hypothesis import given
from hypothesis import strategies as st

from budgetcare.domain.models import GoalFrequency, MoodTier
from budgetcare.domain.schedule import plan_schedule
from budgetcare.domain.scoring import calculate_condition, calculate_mood_tier


@given(
    period_days=st.integers(min_value=2, max_value=365),
    target_cents=st.integers(min_value=200, max_value=10_000_000),
    freq=st.sampled_from([GoalFrequency.DAILY, GoalFrequency.WEEKLY, GoalFrequency.MONTHLY]),
)
def test_schedule_properties(period_days: int, target_cents: int, freq: GoalFrequency):
    tz = ZoneInfo("UTC")
    created_at = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    plan = plan_schedule(
        created_at=created_at,
        tz=tz,
        period_days=period_days,
        frequency=freq,
        target_cents=target_cents,
    )
    if plan is not None:
        # Total feedings must be at least 2
        assert plan.total_feedings >= 2
        assert len(plan.periods) == plan.total_feedings

        # Cut-off dates must be strictly increasing
        cutoffs = [p.end_date for p in plan.periods]
        for i in range(len(cutoffs) - 1):
            assert cutoffs[i] < cutoffs[i + 1]

        # The last cut-off must equal end_date
        assert plan.periods[-1].end_date == plan.end_date

        # Sum of nominals must equal target_cents
        total_nominal = sum(p.nominal_cents for p in plan.periods)
        assert total_nominal == target_cents


@given(
    total_feedings=st.integers(min_value=2, max_value=365),
)
def test_condition_monotonicity(total_feedings: int):
    prev_cond = 100
    for m in range(total_feedings + 1):
        cond = calculate_condition(missed_periods=m, total_feedings=total_feedings)
        assert 0 <= cond <= 100
        # Condition is non-increasing as misses increase
        assert cond <= prev_cond
        prev_cond = cond

        tier = calculate_mood_tier(missed_periods=m, total_feedings=total_feedings)
        if cond == 100 and m == 0:
            assert tier == MoodTier.TIER_4
        elif cond >= 75:
            assert tier == MoodTier.TIER_3
        elif cond >= 50:
            assert tier == MoodTier.TIER_2
        else:
            assert tier == MoodTier.TIER_1
