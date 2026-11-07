from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    Text,
)
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

goal_frequency_enum = PG_ENUM(
    "daily",
    "weekly",
    "monthly",
    name="goal_frequency",
    schema="budget_care",
    create_type=False,
)
goal_status_enum = PG_ENUM(
    "active",
    "graduated",
    "closed",
    name="goal_status",
    schema="budget_care",
    create_type=False,
)
period_status_enum = PG_ENUM(
    "open",
    "completed",
    "missed",
    name="period_status",
    schema="budget_care",
    create_type=False,
)
entry_kind_enum = PG_ENUM(
    "deposit",
    "free_food",
    name="entry_kind",
    schema="budget_care",
    create_type=False,
)
notif_kind_enum = PG_ENUM(
    "reminder",
    "follow_up",
    "early_warning",
    "result",
    name="notif_kind",
    schema="budget_care",
    create_type=False,
)
notif_status_enum = PG_ENUM(
    "pending",
    "sending",
    "sent",
    "skipped",
    "cancelled",
    "failed",
    name="notif_status",
    schema="budget_care",
    create_type=False,
)


class Base(DeclarativeBase):
    metadata = MetaData(schema="budget_care")


class UserTable(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    timezone: Mapped[str | None] = mapped_column(Text, nullable=True)
    variant: Mapped[str] = mapped_column(Text, nullable=False, default="pet")
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    goals: Mapped[list["GoalTable"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    conversation: Mapped["ConversationTable | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    events: Mapped[list["EventTable"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class GoalTable(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    target_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    period_days: Mapped[int] = mapped_column(Integer, nullable=False)
    frequency: Mapped[str] = mapped_column(goal_frequency_enum, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_feedings: Mapped[int] = mapped_column(Integer, nullable=False)
    nominal_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_nominal_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reminder_weekday: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    reminder_dom: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    reminder_on_last: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    species: Mapped[str] = mapped_column(Text, nullable=False)
    pet_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(goal_status_enum, nullable=False, default="active")
    graduated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    user: Mapped["UserTable"] = relationship(back_populates="goals")
    periods: Mapped[list["FeedingPeriodTable"]] = relationship(
        back_populates="goal", cascade="all, delete-orphan", order_by="FeedingPeriodTable.idx"
    )
    entries: Mapped[list["EntryTable"]] = relationship(
        back_populates="goal",
        cascade="all, delete-orphan",
        foreign_keys="[EntryTable.goal_id]",
        overlaps="entries,period",
    )
    notifications: Mapped[list["NotificationTable"]] = relationship(
        back_populates="goal", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("goals_user_idx", "user_id", "status"),
        CheckConstraint("char_length(name) between 1 and 60", name="goals_name_length"),
        CheckConstraint("target_cents > 0", name="goals_target_cents_positive"),
        CheckConstraint("period_days between 2 and 365", name="goals_period_days_range"),
        CheckConstraint("total_feedings >= 2", name="goals_total_feedings_min"),
        CheckConstraint("nominal_cents > 0", name="goals_nominal_cents_positive"),
        CheckConstraint("last_nominal_cents > 0", name="goals_last_nominal_cents_positive"),
    )


class FeedingPeriodTable(Base):
    __tablename__ = "feeding_periods"

    goal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("goals.id", ondelete="CASCADE"), primary_key=True
    )
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    nominal_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(period_status_enum, nullable=False, default="open")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    goal: Mapped["GoalTable"] = relationship(back_populates="periods")
    entries: Mapped[list["EntryTable"]] = relationship(
        back_populates="period", cascade="all, delete-orphan", overlaps="entries,goal"
    )

    __table_args__ = (Index("feeding_periods_due_idx", "cutoff_at"),)


class EntryTable(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    goal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
    )
    period_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(entry_kind_enum, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_feeding: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_update_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    goal: Mapped["GoalTable"] = relationship(
        back_populates="entries", foreign_keys=[goal_id], overlaps="entries,period"
    )
    period: Mapped["FeedingPeriodTable"] = relationship(
        back_populates="entries", overlaps="entries,goal"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["goal_id", "period_idx"],
            ["feeding_periods.goal_id", "feeding_periods.idx"],
            ondelete="CASCADE",
        ),
        Index("entries_goal_idx", "goal_id", id.desc()),
    )


class NotificationTable(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    goal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
    )
    period_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(notif_kind_enum, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(notif_status_enum, nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    goal: Mapped["GoalTable"] = relationship(back_populates="notifications")

    __table_args__ = (
        Index("notifications_due_idx", "due_at"),
        Index("notifications_stale_idx", "claimed_at"),
    )


class ConversationTable(Base):
    __tablename__ = "conversations"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    flow: Mapped[str] = mapped_column(Text, nullable=False)
    step: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    user: Mapped["UserTable"] = relationship(back_populates="conversation")


class ProcessedUpdateTable(Base):
    __tablename__ = "processed_updates"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class JobLockTable(Base):
    __tablename__ = "job_locks"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    locked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_by: Mapped[str | None] = mapped_column(Text, nullable=True)


class TickRunTable(Base):
    __tablename__ = "tick_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class PetImageTable(Base):
    __tablename__ = "pet_images"

    species: Mapped[str] = mapped_column(Text, primary_key=True)
    tier: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    telegram_file_id: Mapped[str] = mapped_column(Text, nullable=False)


class EventTable(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    goal_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("goals.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    props: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    user: Mapped["UserTable | None"] = relationship(back_populates="events")

    __table_args__ = (Index("events_name_time_idx", "name", "occurred_at"),)
