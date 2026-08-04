from langgraph.graph import StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition

from chatbot_agent.state import State
from chatbot_agent.nodes.chatbot import chatbot
from chatbot_agent.tools.postgres import query_database


def build_graph(checkpointer=None):
    builder = StateGraph(State)

    builder.add_node("chatbot", chatbot)
    builder.add_node("tools", ToolNode([query_database]))

    builder.add_edge(START, "chatbot")

    builder.add_conditional_edges(
        "chatbot",
        tools_condition,
    )

    builder.add_edge("tools", "chatbot")

    return builder.compile(checkpointer=checkpointer)