import secrets

from fastapi import Header, HTTPException, status

from budgetcare.config import settings


async def verify_telegram_secret(
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> None:
    if not settings.TELEGRAM_WEBHOOK_SECRET:
        # If no secret configured, fail closed
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook secret not configured",
        )
    if not x_telegram_bot_api_secret_token or not secrets.compare_digest(
        x_telegram_bot_api_secret_token, settings.TELEGRAM_WEBHOOK_SECRET
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram secret token",
        )


async def verify_tick_secret(
    x_tick_secret: str | None = Header(default=None),
) -> None:
    if not settings.TICK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tick secret not configured",
        )
    if not x_tick_secret or not secrets.compare_digest(x_tick_secret, settings.TICK_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Tick secret header",
        )
