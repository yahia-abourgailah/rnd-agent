from langchain_core.messages import SystemMessage

from chatbot_agent.llm_client import get_llm_with_tools
from chatbot_agent.prompts import load_system_prompt
from chatbot_agent.state import State

SYSTEM_PROMPT = SystemMessage(content=load_system_prompt())


def chatbot(state: State) -> dict:
    response = get_llm_with_tools().invoke([SYSTEM_PROMPT, *state["messages"]])
    return {"messages": [response]}
