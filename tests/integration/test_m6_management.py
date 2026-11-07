from datetime import UTC, datetime

import pytest

from budgetcare.db.uow import uow_factory
from budgetcare.services.goals import create_goal_from_wizard
from budgetcare.services.settings import (
    change_user_timezone,
    delete_single_goal,
    toggle_goal_notifications,
    wipe_all_user_data,
)
from budgetcare.services.users import get_or_create_user


@pytest.mark.asyncio
async def test_m6_management_flow_against_database():
    test_tg_id = 999006
    test_chat_id = 888006

    async with uow_factory() as uow:
        # 1. Setup user
        user, _ = await get_or_create_user(uow, test_tg_id, test_chat_id)
        user.timezone = "Asia/Jakarta"
        await uow.session.flush()

        # Clean old test goals
        existing = await uow.goals.list_active_by_user(user.id)
        for g in existing:
            await uow.session.delete(g)
        await uow.session.flush()

        # 2. Create goal
        now = datetime.now(UTC)
        draft = {
            "name": "M6 Management Goal",
            "target_cents": 5000,
            "period_days": 14,
            "frequency": "weekly",
            "species": "rabbit",
            "pet_name": "Bunny",
            "notifications_enabled": True,
            "reminder_weekday": 4,
            "reminder_dom": None,
            "reminder_on_last": False,
        }
        goal = await create_goal_from_wizard(uow, user, draft, now)
        goal_id = goal.id

        # 3. Test toggle notification in DB
        ok = await toggle_goal_notifications(uow, goal_id, enabled=False, now=now)
        assert ok is True
        goal_refreshed = await uow.goals.get_by_id(goal_id)
        assert goal_refreshed is not None
        assert goal_refreshed.notifications_enabled is False

        # 4. Test timezone change in DB
        await change_user_timezone(uow, user.id, new_tz_str="Asia/Makassar", now=now)
        user_refreshed = await uow.users.get_by_id(user.id)
        assert user_refreshed is not None
        assert user_refreshed.timezone == "Asia/Makassar"

        # 5. Test delete single goal in DB
        del_ok = await delete_single_goal(uow, user.id, goal_id)
        assert del_ok is True
        assert await uow.goals.get_by_id(goal_id) is None

        # 6. Test wipe all user data in DB
        wipe_ok = await wipe_all_user_data(uow, user.id)
        assert wipe_ok is True
        await uow.session.flush()
        assert await uow.users.get_by_id(user.id) is None
