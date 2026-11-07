from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from budgetcare.bot.routers.newgoal import InNewGoalWizardFilter
from budgetcare.db.tables import ConversationTable, UserTable


@pytest.mark.asyncio
async def test_in_newgoal_wizard_filter():
    filt = InNewGoalWizardFilter()
    user = UserTable(id=1, telegram_user_id=123, chat_id=123)
    msg = MagicMock(spec=Message)

    # 1. No active conversation -> False
    uow = MagicMock()
    uow.conversations.get = AsyncMock(return_value=None)
    assert await filt(msg, user, uow) is False

    # 2. Different flow conversation (e.g. tz) -> False
    uow.conversations.get = AsyncMock(
        return_value=ConversationTable(user_id=1, flow="tz", step="ask_location")
    )
    assert await filt(msg, user, uow) is False

    # 3. Newgoal wizard conversation -> True
    uow.conversations.get = AsyncMock(
        return_value=ConversationTable(user_id=1, flow="newgoal", step="name")
    )
    assert await filt(msg, user, uow) is True

    # 4. user or uow is None -> False (safe fallback without crash)
    assert await filt(msg, None, None) is False
