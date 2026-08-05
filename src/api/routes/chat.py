"""Chat endpoint — natural-language questions answered in SQL over the catalogue.

Conversation state lives in the checkpointer keyed by `conversation_id`. Callers
omit it on the first message and echo the returned value back on every
follow-up; a new id starts a fresh conversation.
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from langchain_core.messages import HumanMessage

from api.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, http_request: Request) -> ChatResponse:
    graph = getattr(http_request.app.state, "chat_graph", None)
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat agent is not available.",
        )

    conversation_id = request.conversation_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": conversation_id}}

    try:
        result = graph.invoke(
            {"messages": [HumanMessage(content=request.message)]},
            config=config,
        )
    except Exception:
        logger.exception("Chat invocation failed for conversation %s", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The assistant failed to answer. Please retry.",
        ) from None

    return ChatResponse(
        reply=result["messages"][-1].content,
        conversation_id=conversation_id,
    )
