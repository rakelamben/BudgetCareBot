from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, Update

from budgetcare.db.uow import uow_factory
from budgetcare.logging import logger


class UnitOfWorkMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        bot: Bot = data["bot"]
        update_obj: Update | None = data.get("event_update")
        update_id: int | None = update_obj.update_id if update_obj else None

        from_user = data.get("event_from_user")
        if not from_user:
            return await handler(event, data)

        async with uow_factory() as uow:
            # 1. Deduplication via processed_updates
            if update_id is not None:
                is_new_update = await uow.updates.record_if_not_exists(update_id)
                if not is_new_update:
                    logger.info("duplicate_update_skipped", update_id=update_id)
                    return None

            # 2. Upsert user
            chat_id = from_user.id
            if update_obj and update_obj.message and update_obj.message.chat:
                chat_id = update_obj.message.chat.id
            elif update_obj and update_obj.callback_query and update_obj.callback_query.message:
                chat_id = update_obj.callback_query.message.chat.id

            user, _ = await uow.users.upsert_user(
                telegram_user_id=from_user.id,
                chat_id=chat_id,
            )

            # 3. Inject context
            data["uow"] = uow
            data["user"] = user

            # 4. Execute handler
            res = await handler(event, data)

            # 5. Commit transaction
            await uow.commit()

            # 6. Flush staged outgoing replies
            for reply in uow.outgoing_replies:
                try:
                    await bot.send_message(**reply)
                except Exception as e:  # noqa: BLE001
                    logger.warning("failed_sending_staged_reply", error=str(e), reply=reply)

            return res
