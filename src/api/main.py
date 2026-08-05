import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import chat, feedback, health, insights, launches, monitoring
from api.security import require_api_key
from chatbot_agent.checkpointer import conversation_checkpointer
from chatbot_agent.graph import build_graph

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Hold one checkpointer + graph for the process lifetime.

    A failure here degrades /chat to 503 rather than taking the whole API down —
    the insight endpoints do not depend on the agent.
    """
    try:
        with conversation_checkpointer() as checkpointer:
            app.state.chat_graph = build_graph(checkpointer)
            yield
    except Exception:
        logger.exception("Chat agent unavailable; serving the rest of the API")
        app.state.chat_graph = None
        yield


app = FastAPI(title="Launch Intelligence API", lifespan=lifespan)

# The CRM dashboard (React/Next.js, built by the full-stack team) runs on a
# different origin and calls these endpoints from the browser — which the
# browser blocks unless the API opts in via CORS. Restrict allow_origins to the
# CRM's domain in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# /health stays open (liveness/monitoring). Everything that returns data is
# gated behind the API key.
_auth = [Depends(require_api_key)]

app.include_router(health.router)
app.include_router(launches.router, dependencies=_auth)
app.include_router(feedback.router, dependencies=_auth)
app.include_router(insights.router, dependencies=_auth)
app.include_router(monitoring.router, dependencies=_auth)
app.include_router(chat.router, dependencies=_auth)
