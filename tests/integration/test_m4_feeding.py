from datetime import UTC, datetime

import pytest

from budgetcare.db.uow import uow_factory
from budgetcare.services.feeding import feed_goal
from budgetcare.services.goals import create_goal_from_wizard
from budgetcare.services.undo import apply_undo, get_undo_candidate
from budgetcare.services.users import get_or_create_user


@pytest.mark.asyncio
async def test_feeding_and_undo_flow_against_database():
    test_tg_id = 999003
    test_chat_id = 888003

    async with uow_factory() as uow:
        # 1. Setup user with timezone
        user, _ = await get_or_create_user(uow, test_tg_id, test_chat_id)
        user.timezone = "Asia/Jakarta"
        await uow.session.flush()

        # Clean existing test goals if any
        existing_goals = await uow.goals.list_active_by_user(user.id)
        for g in existing_goals:
            await uow.session.delete(g)
        await uow.session.flush()

        # 2. Create a test goal: target $20.00 (2000 cents), period 7 days, daily
        now = datetime.now(UTC)
        draft_data = {
            "name": "Trip M4 Test",
            "target_cents": 2000,
            "period_days": 7,
            "frequency": "daily",
            "species": "cat",
            "pet_name": "Kiki",
            "notifications_enabled": True,
            "reminder_weekday": None,
            "reminder_dom": None,
            "reminder_on_last": False,
        }
        goal = await create_goal_from_wizard(
            uow=uow,
            user=user,
            draft=draft_data,
            now=now,
        )
        assert goal.id is not None
        goal_id = goal.id

        # 3. Log a feeding deposit of $10.00 (1000 cents)
        now = datetime.now(UTC)
        feed_res = await feed_goal(
            uow=uow,
            user_id=user.id,
            goal_id=goal_id,
            amount_cents=1000,
            occurred_at=now,
        )
        assert feed_res.success is True
        assert feed_res.is_graduated is False
        assert feed_res.deposited_cents == 1000
        assert feed_res.target_cents == 2000
        assert feed_res.is_free_food is False

        # 4. Log second deposit of $10.00 to reach $20.00 -> Graduated!
        grad_res = await feed_goal(
            uow=uow,
            user_id=user.id,
            goal_id=goal_id,
            amount_cents=1000,
            occurred_at=now,
        )
        assert grad_res.success is True
        assert grad_res.is_graduated is True
        assert grad_res.deposited_cents == 2000
        assert grad_res.goal.status == "graduated"
        assert grad_res.goal.result is not None
        assert grad_res.goal.result["outcome"] == "graduated"

        grad_entry_id = grad_res.entry.id

        # 5. Find candidate for undo
        candidate = await get_undo_candidate(uow, user.id)
        assert candidate is not None
        assert candidate.id == grad_entry_id

        # 6. Apply undo on graduating entry -> Goal should reopen to active!
        undo_res = await apply_undo(
            uow=uow,
            user_id=user.id,
            entry_id=grad_entry_id,
            now=now,
        )
        assert undo_res.success is True
        assert undo_res.reopened is True
        assert undo_res.goal.status == "active"
        assert undo_res.goal.graduated_at is None
        assert undo_res.goal.result is None
        assert undo_res.deposited_cents == 1000
