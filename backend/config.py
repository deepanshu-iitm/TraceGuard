"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """TraceGuard application settings."""

    app_env: str = "development"
    app_debug: bool = False
    tg_host: str = ""
    tg_graphname: str = "FraudGraph"
    tg_username: str = ""
    tg_password: str = ""
    tg_secret: str = ""
    tg_api_token: str = ""
    tg_tgcloud: bool = True
    openai_api_key: str = ""
    llm_model: str = "gpt-4.1-mini"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()