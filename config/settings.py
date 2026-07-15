import os
from enum import StrEnum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(__file__).resolve().parent

# Which .env file to load is itself chosen by an environment variable, so the
# same image runs in dev/staging/prod just by pointing ENV_FILE at a different
# file (or, in prod, by injecting real env vars and leaving ENV_FILE unset).
ENV_FILE = os.environ.get("ENV_FILE", ".env")


class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    env: Environment = Environment.DEVELOPMENT

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

    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.env is Environment.PRODUCTION

    @property
    def sources_registry_path(self) -> Path:
        """
        Per-environment source registry: config/sources.<env>.yaml if it
        exists, else config/sources.yaml. Lets dev crawl a fake/demo source
        while prod crawls the real ones — adding a source stays one YAML edit.
        """
        env_specific = CONFIG_DIR / f"sources.{self.env.value}.yaml"
        return env_specific if env_specific.exists() else CONFIG_DIR / "sources.yaml"


settings = Settings()

# Back-compat constant for callers that imported this directly. Prefer
# settings.sources_registry_path so the choice stays environment-aware.
SOURCES_REGISTRY_PATH = settings.sources_registry_path
