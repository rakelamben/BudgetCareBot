from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    TICK_SECRET: str = ""
    DATABASE_URL: str = ""
    DATABASE_URL_MIGRATIONS: str = ""
    APP_ENV: str = "local"
    LOG_LEVEL: str = "INFO"
    PET_IMAGE_BASE_URL: str = ""

    CUTOFF_GRACE_SECONDS: int = 60
    TICK_TIME_BUDGET_SECONDS: int = 25
    TICK_LEASE_SECONDS: int = 120
    SEND_RATE_PER_SECOND: int = 25
    SEND_BATCH_SIZE: int = 200
    MAX_NOTIFICATION_ATTEMPTS: int = 3
    STALE_CLAIM_MINUTES: int = 5
    STALE_NOTIFICATION_HOURS: int = 3
    UNDO_WINDOW_HOURS: int = 24

    MIN_NOMINAL_CENTS: int = 100
    MAX_AMOUNT_CENTS: int = 100_000_000
    MAX_ACTIVE_GOALS_PER_USER: int = 100


settings = Settings()
