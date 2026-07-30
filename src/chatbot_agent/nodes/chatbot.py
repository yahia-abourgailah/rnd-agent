from langchain_core.messages import SystemMessage

from chatbot_agent.llm_client import get_llm_with_tools
from chatbot_agent.state import State

# Without this the model invents table names on its first turn and burns a
# round-trip on a failed query. It is prepended per call rather than stored in
# state so it never accumulates across turns.
SYSTEM_PROMPT = SystemMessage(
    content=(
        "You answer questions about Egyptian real-estate launches from a "
        "PostgreSQL database. Call describe_schema before your first query so "
        "you use exact table and column names, then call query_database with a "
        "single read-only SELECT. Aggregate and LIMIT in SQL — at most 100 rows "
        "are returned. Answer only from rows you actually retrieved; if a query "
        "returns nothing, say so rather than guessing."
    )
)


def chatbot(state: State) -> dict:
    response = get_llm_with_tools().invoke([SYSTEM_PROMPT, *state["messages"]])
    return {"messages": [response]}
