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


def test_graph_config_omits_base_url_by_default(monkeypatch):
    """No base_url means ScrapeGraphAI talks to the real OpenAI endpoint."""
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL_TOKENS", raising=False)
    from launch_intel.extract.extractor import build_graph_config

    assert "base_url" not in build_graph_config()["llm"]


def test_graph_config_routes_to_custom_endpoint(monkeypatch):
    """A self-hosted / company gateway is selected purely by config."""
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.internal/v1")
    monkeypatch.setenv("LLM_MODEL_TOKENS", "8192")
    monkeypatch.setenv("EXTRACTION_MODEL", "openai/gemma-4")

    import importlib

    import config.settings as settings_module

    importlib.reload(settings_module)
    import launch_intel.extract.extractor as extractor_module

    importlib.reload(extractor_module)

    llm = extractor_module.build_graph_config()["llm"]
    assert llm["base_url"] == "https://llm.internal/v1"
    assert llm["model"] == "openai/gemma-4"
    assert llm["model_tokens"] == 8192

    # restore module state for the rest of the suite
    monkeypatch.undo()
    importlib.reload(settings_module)
    importlib.reload(extractor_module)


def test_secrets_have_no_baked_in_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    settings = Settings(_env_file=None)
    assert settings.openai_api_key == ""
    assert settings.slack_bot_token == ""
