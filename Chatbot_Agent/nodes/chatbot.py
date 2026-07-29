from config import llm
from state import State


def chatbot(state: State):
    response = llm.invoke(state["messages"])
    return {
        "messages": [response]   # ✅ the whole AIMessage, not .content
    }