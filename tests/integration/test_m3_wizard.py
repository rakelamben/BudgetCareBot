from datetime import UTC, datetime

import pytest

from budgetcare.db.uow import uow_factory
from budgetcare.services.goals import create_goal_from_wizard
from budgetcare.services.users import get_or_create_user, update_timezone_from_coords


@pytest.mark.asyncio
async def test_onboarding_and_timezone_flow():
    test_tg_id = 999001
    test_chat_id = 888001

    async with uow_factory() as uow:
        # Clean up any existing test record
        existing = await uow.users.get_by_telegram_id(test_tg_id)
        if existing:
            await uow.users.delete_user(existing.id)
            await uow.commit()

    async with uow_factory() as uow:
        # 1. /start: Create user
        user, is_new = await get_or_create_user(uow, test_tg_id, test_chat_id)
        assert is_new is True
        assert user.timezone is None
        await uow.commit()

    async with uow_factory() as uow:
        # 2. Location sharing: Set timezone (Jakarta coords: -6.2088, 106.8456)
        user = await uow.users.get_by_telegram_id(test_tg_id)
        assert user is not None

        tz = await update_timezone_from_coords(uow, user.id, lat=-6.2088, lng=106.8456)
        assert tz == "Asia/Jakarta"
        await uow.commit()

    async with uow_factory() as uow:
        # 3. Verify timezone was saved in database
        user = await uow.users.get_by_telegram_id(test_tg_id)
        assert user is not None
        assert user.timezone == "Asia/Jakarta"


@pytest.mark.asyncio
async def test_goal_creation_wizard_flow():
    test_tg_id = 999002
    test_chat_id = 888002

    async with uow_factory() as uow:
        existing = await uow.users.get_by_telegram_id(test_tg_id)
        if existing:
            await uow.users.delete_user(existing.id)
            await uow.commit()

    async with uow_factory() as uow:
        user, _ = await get_or_create_user(uow, test_tg_id, test_chat_id)
        await uow.users.set_timezone(user.id, "Asia/Jakarta")
        await uow.commit()

    async with uow_factory() as uow:
        user = await uow.users.get_by_telegram_id(test_tg_id)
        assert user is not None

        # Simulate wizard draft
        draft = {
            "name": "Trip to Lombok",
            "target_cents": 7000,  # $70.00
            "period_days": 28,  # 28 days
            "frequency": "weekly",  # Weekly: 4 feedings of $17.50
            "species": "hamster",
            "pet_name": "Mochi",
            "notifications_enabled": True,
            "reminder_weekday": 6,  # Sunday
        }

        # Save conversation draft
        await uow.conversations.set_state(user.id, "newgoal", "confirm", draft)
        await uow.commit()

    now = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)

    async with uow_factory() as uow:
        user = await uow.users.get_by_telegram_id(test_tg_id)
        assert user is not None

        conv = await uow.conversations.get(user.id)
        assert conv is not None

        # Confirm and create goal
        goal = await create_goal_from_wizard(uow, user, conv.data, now)
        await uow.commit()

    # Verify atomic DB persistence
    async with uow_factory() as uow:
        created_goal = await uow.goals.get_by_id(goal.id)
        assert created_goal is not None
        assert created_goal.name == "Trip to Lombok"
        assert created_goal.status == "active"
        assert created_goal.total_feedings == 4
        assert created_goal.nominal_cents == 1750

        # Verify periods
        periods = await uow.periods.list_by_goal(goal.id)
        assert len(periods) == 4
        assert [p.idx for p in periods] == [0, 1, 2, 3]

        # Verify conversation state is cleared
        cleared_conv = await uow.conversations.get(user.id)
        assert cleared_conv is None
