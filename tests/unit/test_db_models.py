from budgetcare.db.tables import (
    Base,
    EntryTable,
    GoalTable,
)
from budgetcare.db.uow import UnitOfWork


def test_tables_metadata():
    table_names = set(Base.metadata.tables.keys())
    expected = {
        "budget_care.users",
        "budget_care.goals",
        "budget_care.feeding_periods",
        "budget_care.entries",
        "budget_care.notifications",
        "budget_care.conversations",
        "budget_care.processed_updates",
        "budget_care.job_locks",
        "budget_care.tick_runs",
        "budget_care.pet_images",
        "budget_care.events",
    }
    assert expected.issubset(table_names)
    assert GoalTable.__table__.schema == "budget_care"


def test_goal_table_columns():
    table = GoalTable.__table__
    cols = {c.name for c in table.columns}
    assert "id" in cols
    assert "user_id" in cols
    assert "target_cents" in cols
    assert "period_days" in cols
    assert "frequency" in cols
    assert "status" in cols
    assert "result" in cols


def test_entry_table_columns():
    table = EntryTable.__table__
    cols = {c.name for c in table.columns}
    assert "goal_id" in cols
    assert "period_idx" in cols
    assert "is_feeding" in cols
    assert "undone_at" in cols


def test_uow_initialization():
    class DummySession:
        pass

    session = DummySession()
    uow = UnitOfWork(session)  # type: ignore
    assert uow.users is not None
    assert uow.goals is not None
    assert uow.periods is not None
    assert uow.entries is not None
    assert uow.notifications is not None
    assert uow.conversations is not None
    assert uow.updates is not None
    assert uow.locks is not None
    assert uow.tick_runs is not None
    assert uow.events is not None

    uow.add_reply(chat_id=123, text="Hello")
    assert len(uow.outgoing_replies) == 1
    assert uow.outgoing_replies[0]["chat_id"] == 123
