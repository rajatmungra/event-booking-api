from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables win over .env, so Docker can point at `db` instead of localhost.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str


settings = Settings()
