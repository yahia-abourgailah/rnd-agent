from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from chatbot_agent.state import State
from chatbot_agent.nodes.chatbot import chatbot
from chatbot_agent.tools.postgres import query_database

builder = StateGraph(State)

# Nodes
builder.add_node("chatbot", chatbot)
builder.add_node("tools", ToolNode([query_database]))

builder.add_edge(START, "chatbot")
# If the LLM requested a tool -> go to ToolNode
# Otherwise -> END
builder.add_conditional_edges(
    "chatbot",
    tools_condition,
)

# After the tool finishes, go back to the chatbot
builder.add_edge("tools", "chatbot")
# builder.add_edge("chatbot", END)

graph = builder.compile()