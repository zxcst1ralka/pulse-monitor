from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore", hide_input_in_errors=True)

    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = False
    frontend_url: str = "http://localhost"
    extra_origins: str = ""
    database_url: str
    redis_url: str
    jwt_secret_key: SecretStr
    jwt_access_token_expire_minutes: int = Field(15, ge=1, le=60)
    jwt_refresh_token_expire_days: int = Field(7, ge=1, le=30)
    max_monitors_per_user: int = Field(20, ge=1, le=200)
    check_retention_days: int = Field(30, ge=30, le=90)
    demo_mode: bool = False
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_bot_username: str = ""

    @property
    def origins(self) -> list[str]:
        return [self.frontend_url.rstrip("/"), *(
            origin.strip().rstrip("/") for origin in self.extra_origins.split(",") if origin.strip()
        )]

    @property
    def secure_cookies(self) -> bool:
        return self.frontend_url.startswith("https://")

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token.get_secret_value() and self.telegram_bot_username)

    @model_validator(mode="after")
    def validate_deployment(self):
        if len(self.jwt_secret_key.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET_KEY must have at least 32 characters")
        if not self.database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        for origin in self.origins:
            url = urlsplit(origin)
            if url.scheme not in {"http", "https"} or not url.hostname or url.path or url.query or url.fragment or url.username:
                raise ValueError("FRONTEND_URL and EXTRA_ORIGINS must be explicit HTTP(S) origins")
        if self.app_env == "production" and (
            any(not origin.startswith("https://") for origin in self.origins) or self.demo_mode or self.app_debug
        ):
            raise ValueError("Production requires HTTPS origins with debug and demo mode disabled")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
