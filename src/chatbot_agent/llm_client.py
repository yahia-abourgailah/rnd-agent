"""Chat model for the agent, configured from `config.settings`.

Points at the self-hosted OpenAI-compatible endpoint (`LLM_BASE_URL`) shared
with the extraction stage — the "openai" provider selects the API dialect, not
the vendor. Nothing here reads os.environ or loads a .env directly; the
ENV_FILE mechanism in config/settings.py stays the single source of truth.
"""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from chatbot_agent.tools.postgres import TOOLS
from config.settings import settings

# Self-hosted endpoints usually ignore the key, but the OpenAI client refuses to
# start without one, so a placeholder stands in when none is configured.
_PLACEHOLDER_API_KEY = "not-needed"


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Built on first use, not at import time, so importing the graph (or
    running tests) never requires a reachable model endpoint."""
    kwargs: dict = {
        "model": settings.chatbot_model,
        "model_provider": "openai",
        "api_key": settings.openai_api_key or _PLACEHOLDER_API_KEY,
    }
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url
    return init_chat_model(**kwargs)


@lru_cache(maxsize=1)
def get_llm_with_tools() -> BaseChatModel:
    """The model the chatbot node calls: same model, with the SQL tools bound."""
    return get_llm().bind_tools(TOOLS)
