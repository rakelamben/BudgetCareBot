from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class GoalFrequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class GoalStatus(str, Enum):
    ACTIVE = "active"
    GRADUATED = "graduated"
    EXPIRED = "expired"


class PeriodStatus(str, Enum):
    OPEN = "open"
    FED = "fed"
    MISSED = "missed"


class EntryKind(str, Enum):
    DEPOSIT = "deposit"
    FREE_FOOD = "free_food"


class NotifKind(str, Enum):
    REMINDER = "reminder"
    FOLLOW_UP = "follow_up"
    EARLY_WARNING = "early_warning"
    RESULT = "result"


class NotifStatus(str, Enum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    FAILED = "failed"


class MoodTier(int, Enum):
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3
    TIER_4 = 4


@dataclass(frozen=True)
class PlannedPeriod:
    idx: int
    start_date: date
    end_date: date
    cutoff_at: datetime  # UTC instant
    nominal_cents: int


@dataclass(frozen=True)
class SchedulePlan:
    frequency: GoalFrequency
    periods: list[PlannedPeriod]
    total_feedings: int
    nominal_cents: int
    last_nominal_cents: int
    start_date: date
    end_date: date
    start_at: datetime  # UTC instant


@dataclass(frozen=True)
class OfferedFrequency:
    frequency: GoalFrequency
    plan: SchedulePlan


@dataclass(frozen=True)
class PlannedNotification:
    period_idx: int
    kind: NotifKind
    due_at: datetime  # UTC instant with jitter


@dataclass(frozen=True)
class GoalResult:
    outcome: str
    final_condition_pct: int
    final_quality_pct: int
    mood_tier: int
    title: str
    days_taken: int
    deposited_cents: int
    surplus_cents: int
    free_food_count: int
    closed_at: datetime
