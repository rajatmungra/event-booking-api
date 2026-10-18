from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables win over .env, so Docker can point at `db` instead of localhost.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    # HS256 needs a key of at least 32 bytes to be secure.
    jwt_secret: str = Field(min_length=32)
    # Only the test suite uses this; the app never connects to it.
    test_database_url: str | None = None


settings = Settings()
