"""
Tests for the layered configuration: env vars beat defaults, ENV selects the
per-environment source registry, and no secret has a real default baked in.
"""

from config.settings import CONFIG_DIR, Environment, Settings


def test_defaults_are_development(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    settings = Settings(_env_file=None)
    assert settings.env is Environment.DEVELOPMENT
    assert settings.is_production is False


def test_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("EXTRACTION_MODEL", "gpt-4o")
    settings = Settings(_env_file=None)
    assert settings.env is Environment.PRODUCTION
    assert settings.is_production is True
    assert settings.extraction_model == "gpt-4o"


def test_registry_path_follows_environment(monkeypatch):
    monkeypatch.setenv("ENV", "development")
    assert Settings(_env_file=None).sources_registry_path == (
        CONFIG_DIR / "sources.development.yaml"
    )

    monkeypatch.setenv("ENV", "production")
    assert Settings(_env_file=None).sources_registry_path == (
        CONFIG_DIR / "sources.production.yaml"
    )


def test_registry_path_falls_back_when_env_file_missing(monkeypatch):
    # No sources.staging.yaml exists -> fall back to the base registry
    monkeypatch.setenv("ENV", "staging")
    assert Settings(_env_file=None).sources_registry_path == CONFIG_DIR / "sources.yaml"


def test_secrets_have_no_baked_in_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    settings = Settings(_env_file=None)
    assert settings.openai_api_key == ""
    assert settings.slack_bot_token == ""
