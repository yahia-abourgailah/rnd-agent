from config import llm
from state import State


def chatbot(state: State):
    response = llm.invoke(state["messages"])

    return {
        "response": response.content
    }