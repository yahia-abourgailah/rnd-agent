"""Chat endpoint — natural-language questions answered in SQL over the catalogue.

Conversation state lives in the checkpointer keyed by `conversation_id`. Callers
omit it on the first message and echo the returned value back on every
follow-up; a new id starts a fresh conversation.
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError

from api.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

# describe_schema, then a query, then at most a few corrections. A model that
# has not answered by then is looping on failing SQL, not converging.
MAX_STEPS = 12

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
    config = {
        "configurable": {"thread_id": conversation_id},
        "recursion_limit": MAX_STEPS,
    }

    try:
        result = graph.invoke(
            {"messages": [HumanMessage(content=request.message)]},
            config=config,
        )
    except GraphRecursionError:
        # The model looped on failing queries instead of answering. Distinct
        # from a crash, and the distinction is the whole point of logging a
        # stop reason: this one is a prompt or schema problem, not an outage.
        logger.warning(
            "chat stop_reason=max_steps conversation=%s steps=%s", conversation_id, MAX_STEPS
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The assistant could not reach an answer. Try a narrower question.",
        ) from None
    except Exception:
        logger.exception("chat stop_reason=error conversation=%s", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The assistant failed to answer. Please retry.",
        ) from None

    logger.info(
        "chat stop_reason=complete conversation=%s messages=%d",
        conversation_id,
        len(result["messages"]),
    )
    return ChatResponse(
        reply=result["messages"][-1].content,
        conversation_id=conversation_id,
    )
