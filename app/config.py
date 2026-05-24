from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    anthropic_api_key: str
    agent_model: str = "claude-haiku-4-5-20251001"
    database_url: str
    otel_exporter_otlp_endpoint: str
    jwt_secret: str
    slack_bot_token: str | None = None
    slack_portfolio_channel: str = "portfolio-pulse"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()  # type: ignore[call-arg]
