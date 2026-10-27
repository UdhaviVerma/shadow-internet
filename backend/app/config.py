from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: Literal["development", "test", "production"] = "development"
    auth_mode: Literal["demo", "development", "clerk"] = "demo"
    database_url: str = "sqlite:///./shadow.db"
    redis_url: str | None = None
    queue_mode: Literal["inline", "celery"] = "inline"
    frontend_origin: str = "http://localhost:3000"
    clerk_issuer: str | None = None
    clerk_audience: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    scan_limit_per_hour: int = 10
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def production_requirements(self):
        if self.environment == "production":
            if self.auth_mode == "development":
                raise ValueError("Development authentication is forbidden in production")
            if not self.database_url.startswith("postgresql+psycopg://"):
                raise ValueError("Production requires persistent PostgreSQL")
            if self.auth_mode == "clerk" and (not self.redis_url or self.queue_mode != "celery"):
                raise ValueError("Live production scans require Redis and a Celery worker")
        if self.auth_mode == "clerk" and (not self.clerk_issuer or not self.clerk_issuer.startswith("https://")):
            raise ValueError("Clerk authentication requires an HTTPS CLERK_ISSUER")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
