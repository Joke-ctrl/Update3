"""
Application configuration.
Loaded from environment variables (see .env.example).
"""
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "THE MARKET KILL3R"
    APP_ENV: str = Field(default="development")
    DEBUG: bool = Field(default=False)
    API_V1_PREFIX: str = "/api/v1"

    # Security
    SECRET_KEY: str = Field(default="CHANGE_ME_IN_PRODUCTION")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Database
    DATABASE_URL: str = Field(default="sqlite:///./dev.db")

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        # Railway's (and Heroku's) managed Postgres plugin commonly injects
        # a DATABASE_URL starting with the legacy "postgres://" scheme.
        # SQLAlchemy 1.4+ dropped that alias and raises NoSuchModuleError
        # at create_engine() time, which crashes the app on import before
        # it ever binds a port. Normalize it here so this can never bite us.
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v

    # CORS
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    # Email (SMTP) - used by app/notifications/email.py for admin
    # registration-approval and login-OTP notices.
    SMTP_HOST: str = Field(default="")
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str = Field(default="")
    SMTP_PASSWORD: str = Field(default="")
    SMTP_USE_TLS: bool = Field(default=True)
    EMAIL_FROM: str = Field(default="noreply@marketkill3r.app")

    # Telegram Bot API - used by app/notifications/telegram.py as the
    # primary channel for BOTH registration-approval codes and login
    # OTPs, ahead of the email fallback for each. All values come from
    # environment variables only; never hard-code the bot token or chat
    # ID, and never commit them to source control.
    TELEGRAM_ENABLED: bool = Field(default=True)
    TELEGRAM_API_URL: str = Field(default="https://api.telegram.org")
    # Bot token from @BotFather (format "123456:ABC-DEF...").
    TELEGRAM_BOT_TOKEN: str = Field(default="")
    # The admin's Telegram chat_id (not a phone number) — Telegram Bot
    # API delivery is addressed by chat_id, obtained by messaging your
    # bot once and reading it back from getUpdates. See
    # app/notifications/telegram.py for the exact steps.
    TELEGRAM_CHAT_ID: str = Field(default="")

    # Admin-gated auth (registration approval + optional login OTP).
    # Registration-approval codes go to the admin (Telegram, falling back
    # to this email) for manual review — never to the registering user.
    # Login OTPs also go to the admin's Telegram chat first now, falling
    # back to the logging-in user's own email only if Telegram fails.
    ADMIN_EMAIL: str = Field(default="privateinv08@gmail.com")
    REGISTRATION_CODE_LENGTH: int = Field(default=8)
    REGISTRATION_CODE_EXPIRE_MINUTES: int = Field(default=60 * 24 * 3)  # 3 days
    LOGIN_OTP_ENABLED: bool = Field(default=True)
    LOGIN_OTP_LENGTH: int = Field(default=6)
    LOGIN_OTP_EXPIRE_MINUTES: int = Field(default=10)

    # MT5 / external
    MT5_API_KEY: str = Field(default="")

    # Optional free market-data providers. Keep keys in .env, never source.
    # Live-Rates works keyless at a small free quota and supports XAU/USD, US30
    # and major FX; a key can raise the quota.
    LIVE_RATES_URL: str = Field(default="https://live-rates.com/api/rates")
    LIVE_RATES_API_KEY: str = Field(default="")
    # XAUS provides keyless XAU/USD spot data with a reasonable-use policy.
    XAUS_SPOT_URL: str = Field(default="https://xaus.com/api/v1/spot")
    # Twelve Data Basic is useful for internal development/backfill; its free
    # plan is not intended for external/display redistribution.
    TWELVE_DATA_API_KEY: str = Field(default="")
    # Optional FMP calendar fallback.
    FMP_API_KEY: str = Field(default="")

    # Economic calendar (JBlanked Calendar API - see app/services/economic_calendar.py)
    CALENDAR_API_KEY: str = Field(default="")

    # News RSS sources for sentiment (comma-effectively a list here; override
    # via env if CNBC's feeds are unreachable from your deployment's IP)
    NEWS_RSS_FEEDS: List[str] = Field(
        default_factory=lambda: [
            "https://www.cnbc.com/id/10000664/device/rss/rss.html",  # CNBC Finance
            "https://www.cnbc.com/id/15839135/device/rss/rss.html",  # CNBC Business
        ]
    )

    # Anthropic (AI engine, later phase)
    ANTHROPIC_API_KEY: str = Field(default="")
    DEFAULT_ANALYSIS_TIMEFRAMES: List[str] = Field(default_factory=lambda: ["H4", "H1", "M15"])
    ANALYSIS_MIN_BARS: int = 100

    @model_validator(mode="after")
    def validate_production_security(self):
        if self.APP_ENV in ("production", "staging") and self.SECRET_KEY == "CHANGE_ME_IN_PRODUCTION":
            raise ValueError("SECRET_KEY must be explicitly configured outside development.")
        if self.APP_ENV in ("production", "staging") and "*" in self.CORS_ORIGINS:
            raise ValueError("CORS_ORIGINS cannot contain '*' in production/staging.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
