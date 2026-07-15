from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_REGISTRY_PATH = Path(__file__).resolve().parent / "sources.yaml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database (TODO(phase-later): consumed once db/engine.py is implemented) ---
    database_url: str = "postgresql+psycopg://launch_intel:launch_intel@localhost:5432/launch_intel"

    # --- Redis / Celery (TODO(phase-later)) ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"

    # --- LLM extraction ---
    openai_api_key: str = ""
    extraction_model: str = "gpt-4o-mini"

    # --- Slack (TODO(phase-later)) ---
    slack_bot_token: str = ""
    slack_alert_channel: str = "#launch-alerts"

    # --- Crawling ---
    playwright_headless: bool = True
    default_request_timeout_seconds: float = 30.0
    default_rate_limit_per_host_seconds: float = Field(
        default=2.0,
        description="Minimum delay between requests to the same host.",
    )

    env: str = "development"
    log_level: str = "INFO"


settings = Settings()
