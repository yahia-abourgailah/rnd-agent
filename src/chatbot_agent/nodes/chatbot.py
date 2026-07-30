from chatbot_agent.llm_client import llm, llm_with_tools
from chatbot_agent.state import State


def chatbot(state: State):
    response = llm_with_tools.invoke(state["messages"])
    return {
        "messages": [response]
    }
