from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_expires_minutes: int = 30
    timezone: str = "America/Lima"


settings = Settings()  # type: ignore[call-arg]
