from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables win over .env, so Docker can point at `db` instead of localhost.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    # HS256 needs a key of at least 32 bytes to be secure.
    jwt_secret: str = Field(min_length=32)
    # Only the test suite uses this; the app never connects to it.
    test_database_url: str | None = None
    # Password for the demo users created by scripts/seed.py; only the seed script reads it.
    seed_password: str | None = Field(default=None, min_length=8)

    @field_validator("database_url", "test_database_url")
    @classmethod
    def use_asyncpg_driver(cls, url: str | None) -> str | None:
        # Hosting providers (e.g. Render) give "postgresql://..." or "postgres://...", but the
        # async engine needs the driver in the URL: "postgresql+asyncpg://...".
        if url is None:
            return None
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+asyncpg://" + url.removeprefix(prefix)
        return url


settings = Settings()
